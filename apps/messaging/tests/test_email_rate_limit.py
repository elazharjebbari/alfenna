from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.core.cache import cache

from apps.accounts.forms_password_reset import OutboxPasswordResetForm
from apps.accounts.models import StudentProfile
from apps.accounts.services import enqueue_email_verification
from apps.messaging.models import OutboxEmail
from apps.messaging.template_loader import FileSystemTemplateLoader


RATE_SETTINGS = {
    "password_reset": {
        "window_seconds": 300,
        "max_per_window": 5,
        "include_failed": True,
    },
    "email_verification": {
        "window_seconds": 300,
        "max_per_window": 5,
        "include_failed": True,
    },
}


@override_settings(EMAIL_RATE_LIMIT=RATE_SETTINGS)
class EmailRateLimiterTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        FileSystemTemplateLoader().sync()
        user_model = get_user_model()
        cls.user = user_model.objects.create_user(
            username="rate-user",
            email="rate@example.com",
            password="StrongPass123!",
        )
        StudentProfile.objects.get_or_create(user=cls.user)

    def setUp(self) -> None:
        cache.clear()
        self.factory = RequestFactory()

    def test_email_verification_is_suppressed_after_limit(self) -> None:
        with patch("apps.messaging.rate_limiter.time.time", return_value=1_000_000):
            for _ in range(5):
                enqueue_email_verification(self.user)
            enqueue_email_verification(self.user)

        qs = OutboxEmail.objects.filter(purpose="email_verification", metadata__user_id=self.user.id)
        self.assertEqual(qs.count(), 6)
        self.assertEqual(qs.filter(status=OutboxEmail.Status.SUPPRESSED).count(), 1)
        dedup = list(qs.values_list("dedup_key", flat=True))
        self.assertEqual(len(dedup), len(set(dedup)))

    def test_window_rollover_allows_additional_emails(self) -> None:
        with patch("apps.messaging.rate_limiter.time.time", return_value=2_000_000):
            for _ in range(5):
                enqueue_email_verification(self.user)
        with patch("apps.messaging.rate_limiter.time.time", return_value=2_000_000 + RATE_SETTINGS["email_verification"]["window_seconds"]):
            enqueue_email_verification(self.user)

        qs = OutboxEmail.objects.filter(purpose="email_verification", metadata__user_id=self.user.id)
        self.assertEqual(qs.count(), 6)
        self.assertEqual(qs.filter(status=OutboxEmail.Status.SUPPRESSED).count(), 0)

    def test_password_reset_rate_limit_matches_policy(self) -> None:
        request = self.factory.post("/accounts/password-reset/")
        request.user = self.user

        with patch("apps.messaging.rate_limiter.time.time", return_value=3_000_000):
            for _ in range(5):
                self._trigger_password_reset(request)
            self._trigger_password_reset(request)

        qs = OutboxEmail.objects.filter(purpose="password_reset", metadata__user_id=self.user.id)
        self.assertEqual(qs.count(), 6)
        self.assertEqual(qs.filter(status=OutboxEmail.Status.SUPPRESSED).count(), 1)

    def _trigger_password_reset(self, request) -> None:
        form = OutboxPasswordResetForm(data={"email": self.user.email})
        self.assertTrue(form.is_valid())
        form.save(request=request)
