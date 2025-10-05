from __future__ import annotations

import os
import json

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lumierelearning.settings.test_cli")

import django

django.setup()

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.accounts.models import StudentProfile
from apps.messaging.constants import (
    TOKEN_NAMESPACE_ACCOUNTS,
    TOKEN_PURPOSE_UNSUBSCRIBE,
    TOKEN_PURPOSE_VERIFY_EMAIL,
)
from apps.messaging.models import EmailTemplate, OutboxEmail
from apps.messaging.tokens import TokenService

UserModel = get_user_model()


@override_settings(ROOT_URLCONF="lumierelearning.urls")
class MessagingEndpointsTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.user = UserModel.objects.create_user(username="testuser", email="user@example.com", password="initial123")
        profile, created = StudentProfile.objects.get_or_create(user=self.user)
        if created:
            profile.email_verified = False
            profile.marketing_opt_in = True
            profile.save(update_fields=["email_verified", "marketing_opt_in"])
        else:
            StudentProfile.objects.filter(pk=profile.pk).update(
                email_verified=False,
                marketing_opt_in=True,
                marketing_opt_out_at=None,
            )
        EmailTemplate.objects.get_or_create(
            slug="accounts/reset",
            locale="fr",
            defaults={
                "version": 1,
                "subject": "Reset",
                "html_template": "<p>Reset {{ reset_url }}</p>",
                "text_template": "Reset {{ reset_url }}",
            },
        )

    def test_verify_email_endpoint_marks_profile(self) -> None:
        token = TokenService.make_signed(
            namespace=TOKEN_NAMESPACE_ACCOUNTS,
            purpose=TOKEN_PURPOSE_VERIFY_EMAIL,
            claims={"user_id": self.user.id},
        )
        response = self.client.get(reverse("messaging:verify-email"), {"t": token, "redirect": 0})
        self.assertEqual(response.status_code, 200)
        profile = StudentProfile.objects.get(user=self.user)
        self.assertTrue(profile.email_verified)
        self.assertIsNotNone(profile.email_verified_at)

    def test_verify_email_endpoint_redirect_mode(self) -> None:
        token = TokenService.make_signed(
            namespace=TOKEN_NAMESPACE_ACCOUNTS,
            purpose=TOKEN_PURPOSE_VERIFY_EMAIL,
            claims={"user_id": self.user.id},
        )
        response = self.client.get(reverse("messaging:verify-email"), {"t": token})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("pages:verification_success"))

    def test_verify_email_missing_token(self) -> None:
        response = self.client.get(reverse("messaging:verify-email"), {"redirect": 0})
        self.assertEqual(response.status_code, 400)

    def test_unsubscribe_endpoint_updates_profile(self) -> None:
        token = TokenService.make_signed(
            namespace=TOKEN_NAMESPACE_ACCOUNTS,
            purpose=TOKEN_PURPOSE_UNSUBSCRIBE,
            claims={"user_id": self.user.id},
        )
        response = self.client.get(reverse("messaging:unsubscribe"), {"t": token})
        self.assertEqual(response.status_code, 200)
        profile = StudentProfile.objects.get(user=self.user)
        self.assertFalse(profile.marketing_opt_in)
        self.assertIsNotNone(profile.marketing_opt_out_at)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_password_reset_request_enqueues_email(self) -> None:
        response = self.client.post(
            reverse("messaging:password-reset-request"),
            data=json.dumps({"email": "user@example.com"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(OutboxEmail.objects.filter(template_slug="accounts/reset").count(), 1)
        outbox = OutboxEmail.objects.get(template_slug="accounts/reset")
        reset_url = outbox.context.get("reset_url", "")
        self.assertIn("/accounts/password-reset/confirm/", reset_url)
        self.assertNotIn("?uid=", reset_url)

    def test_password_reset_confirm_changes_password(self) -> None:
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        response = self.client.post(
            reverse("messaging:password-reset-confirm"),
            data=json.dumps({"uid": uid, "token": token, "new_password": "StrongPass!42"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("StrongPass!42"))

    def test_password_reset_confirm_invalid_token(self) -> None:
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        response = self.client.post(
            reverse("messaging:password-reset-confirm"),
            data=json.dumps({"uid": uid, "token": "invalid", "new_password": "StrongPass!42"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
