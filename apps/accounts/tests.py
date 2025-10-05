from __future__ import annotations

import os
from urllib.parse import parse_qs, urlparse

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lumierelearning.settings.test_cli")

import django

django.setup()

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.test import TestCase, override_settings
from unittest.mock import patch
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.accounts.forms_signup import SignupForm
from apps.accounts.models import StudentProfile
from apps.messaging.constants import (
    EMAIL_VERIFICATION_TTL_SECONDS,
    TOKEN_NAMESPACE_ACCOUNTS,
    TOKEN_PURPOSE_ACTIVATION,
    TOKEN_PURPOSE_VERIFY_EMAIL,
)
from apps.messaging.models import OutboxEmail
from apps.messaging.template_loader import FileSystemTemplateLoader
from apps.messaging.tokens import TokenService

UserModel = get_user_model()


class SignupFormTests(TestCase):
    def test_signup_form_valid_creates_profile(self) -> None:
        form = SignupForm(
            data={
                "full_name": "Alice Example",
                "email": "alice@example.com",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
                "marketing_opt_in": True,
            }
        )
        self.assertTrue(form.is_valid())
        user = form.save()

        self.assertEqual(user.email, "alice@example.com")
        profile = StudentProfile.objects.get(user=user)
        self.assertTrue(profile.marketing_opt_in)
        self.assertIsNone(profile.marketing_opt_out_at)

    def test_signup_form_duplicate_email_is_invalid(self) -> None:
        UserModel.objects.create_user(username="existing", email="dup@example.com", password="Password123!")

        form = SignupForm(
            data={
                "full_name": "Dup User",
                "email": "dup@example.com",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_signup_form_opt_out_sets_timestamp(self) -> None:
        before = timezone.now()
        form = SignupForm(
            data={
                "full_name": "Opt Out",
                "email": "optout@example.com",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            }
        )
        self.assertTrue(form.is_valid())
        user = form.save()
        profile = StudentProfile.objects.get(user=user)
        self.assertFalse(profile.marketing_opt_in)
        self.assertIsNotNone(profile.marketing_opt_out_at)
        self.assertGreaterEqual(profile.marketing_opt_out_at, before)


class SignupViewTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        FileSystemTemplateLoader().sync()

    def test_register_creates_user_and_enqueues_verification(self) -> None:
        response = self.client.post(
            reverse("accounts:register"),
            data={
                "full_name": "Bob Example",
                "email": "bob@example.com",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
                "marketing_opt_in": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        check_email_url = reverse("pages:check_email")
        self.assertTrue(response["Location"].startswith(check_email_url))
        session = self.client.session
        self.assertEqual(session.get("accounts:pending_email"), "bob@example.com")

        user = UserModel.objects.get(email="bob@example.com")
        profile = StudentProfile.objects.get(user=user)
        self.assertTrue(profile.marketing_opt_in)

        outbox = OutboxEmail.objects.get(purpose="email_verification")
        self.assertEqual(outbox.namespace, "accounts")
        self.assertIn("verify", outbox.template_slug)
        self.assertIn("bob@example.com", outbox.to)

        verification_url = outbox.context.get("verification_url", "")
        parsed = urlparse(verification_url)
        self.assertEqual(parsed.path, reverse("messaging:verify-email"))
        params = parse_qs(parsed.query)
        token = params.get("t", [""])[0]
        self.assertIn("+", token)
        payload = TokenService.read_signed(
            token,
            namespace=TOKEN_NAMESPACE_ACCOUNTS,
            purpose=TOKEN_PURPOSE_VERIFY_EMAIL,
            ttl_seconds=EMAIL_VERIFICATION_TTL_SECONDS,
        )
        self.assertEqual(payload.claims.get("user_id"), user.id)

        follow = self.client.get(check_email_url)
        self.assertEqual(follow.status_code, 200)
        self.assertIsNone(self.client.session.get("accounts:pending_email"))

    def test_register_duplicate_email_renders_error(self) -> None:
        UserModel.objects.create_user(username="dup", email="dup2@example.com", password="Password123!")
        response = self.client.post(
            reverse("accounts:register"),
            data={
                "full_name": "Dup User",
                "email": "dup2@example.com",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(OutboxEmail.objects.filter(purpose="email_verification").count(), 0)


class PasswordResetFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        FileSystemTemplateLoader().sync()
        cls.user = UserModel.objects.create_user(
            username="reset-user",
            email="reset@example.com",
            password="StrongPass123!",
        )
        StudentProfile.objects.get_or_create(user=cls.user)

    def test_password_reset_request_enqueues_outbox(self) -> None:
        response = self.client.post(
            reverse("accounts:password_reset"),
            data={"email": "reset@example.com", "next": "/cours/"},
            follow=False,
        )
        self.assertEqual(response.status_code, 302)
        done_url = reverse("accounts:password_reset_done")
        self.assertTrue(response["Location"].startswith(done_url))
        self.assertIn("next=%2Fcours%2F", response["Location"])
        outbox = OutboxEmail.objects.get(purpose="password_reset")
        self.assertIn("reset@example.com", outbox.to)
        self.assertIn("http", outbox.rendered_html)
        self.assertNotEqual(outbox.rendered_html.strip(), "")
        self.assertIn("/accounts/password-reset/confirm/", outbox.rendered_html)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    @patch("apps.messaging.services.schedule_outbox_drain")
    def test_password_reset_request_triggers_scheduler_each_time(self, mock_schedule) -> None:
        OutboxEmail.objects.filter(purpose="password_reset").delete()

        payload = {"email": "reset@example.com"}
        with patch("apps.messaging.services.transaction.on_commit", side_effect=lambda fn: fn()):
            first = self.client.post(reverse("accounts:password_reset"), data=payload, follow=False)
        self.assertEqual(first.status_code, 302)
        self.assertEqual(
            OutboxEmail.objects.filter(purpose="password_reset").count(),
            1,
        )
        self.assertTrue(mock_schedule.called)

        mock_schedule.reset_mock()

        with patch("apps.messaging.services.transaction.on_commit", side_effect=lambda fn: fn()):
            second = self.client.post(reverse("accounts:password_reset"), data=payload, follow=False)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(
            OutboxEmail.objects.filter(purpose="password_reset").count(),
            2,
        )
        self.assertTrue(mock_schedule.called)


class EmailVerificationFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        FileSystemTemplateLoader().sync()

    def setUp(self) -> None:
        self.user = UserModel.objects.create_user(
            username="login-user",
            email="login@example.com",
            password="StrongPass123!",
        )
        profile, _ = StudentProfile.objects.get_or_create(user=self.user)
        profile.email_verified = False
        profile.save(update_fields=["email_verified"])

    def test_login_unverified_user_enqueues_verification_email(self) -> None:
        OutboxEmail.objects.all().delete()

        response = self.client.post(
            reverse("pages:login"),
            data={"username": "login@example.com", "password": "StrongPass123!"},
            follow=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(reverse("pages:check_email")))

        outbox = OutboxEmail.objects.filter(purpose="email_verification", metadata__user_id=self.user.id)
        self.assertEqual(outbox.count(), 1)
        session = self.client.session
        self.assertTrue(session.get("accounts:verification_just_sent", False))

    def test_resend_verification_page_renders(self) -> None:
        self.client.force_login(self.user)
        response = self.client.get(reverse("accounts:resend_verification"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Renvoyer le lien de vérification")

    def test_resend_verification_post_enqueues_when_cooldown_allows(self) -> None:
        OutboxEmail.objects.all().delete()

        self.client.force_login(self.user)
        session = self.client.session
        session["accounts:verification_last_sent_ts"] = timezone.now().timestamp() - 120
        if "accounts:verification_just_sent" in session:
            del session["accounts:verification_just_sent"]
        session.save()

        response = self.client.post(reverse("accounts:resend_verification"), follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].endswith(reverse("accounts:resend_verification")))

        outbox = OutboxEmail.objects.filter(purpose="email_verification", metadata__user_id=self.user.id)
        self.assertEqual(outbox.count(), 1)
        session = self.client.session
        self.assertTrue(session.get("accounts:verification_just_sent", False))

@override_settings(ROOT_URLCONF="lumierelearning.urls")
class PasswordResetAliasTests(TestCase):
    def test_root_alias_redirects_to_namespaced_done(self) -> None:
        response = self.client.get("/password-reset/done/")
        self.assertEqual(response.status_code, 301)
        self.assertTrue(response["Location"].endswith("/accounts/password-reset/done/"))

    def test_root_alias_password_reset_redirects_to_accounts(self) -> None:
        response = self.client.get("/password-reset/")
        self.assertEqual(response.status_code, 301)
        self.assertTrue(response["Location"].endswith("/accounts/password-reset/"))

    def test_french_alias_preserves_uid_and_token(self) -> None:
        uid = "Mw"
        token = "set-token"
        response = self.client.get(f"/mot-de-passe-oublie/definir/{uid}/{token}/")
        self.assertEqual(response.status_code, 301)
        expected = reverse("accounts:password_reset_confirm", kwargs={"uidb64": uid, "token": token})
        self.assertTrue(response["Location"].endswith(expected))

    def test_querystring_fallback_redirects_to_canonical(self) -> None:
        uid = "Mg"
        token = "reset-token"
        response = self.client.get("/accounts/reset/confirm/", {"uid": uid, "token": token})
        self.assertEqual(response.status_code, 302)
        expected = reverse("accounts:password_reset_confirm", kwargs={"uidb64": uid, "token": token})
        self.assertEqual(response["Location"], expected)

    def test_querystring_fallback_requires_parameters(self) -> None:
        response = self.client.get("/accounts/reset/confirm/")
        self.assertEqual(response.status_code, 400)

    def test_querystring_fallback_preserves_next_parameter(self) -> None:
        uid = "Mg"
        token = "reset-token"
        response = self.client.get(
            "/accounts/reset/confirm/",
            {"uid": uid, "token": token, "next": "/cours/"},
        )
        self.assertEqual(response.status_code, 302)
        expected = reverse("accounts:password_reset_confirm", kwargs={"uidb64": uid, "token": token})
        self.assertEqual(response["Location"], f"{expected}?next=%2Fcours%2F")


class ActivateAccountViewTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.user_no_password = UserModel.objects.create_user(
            username="activate-user",
            email="activate@example.com",
        )
        cls.user_no_password.set_unusable_password()
        cls.user_no_password.is_active = False
        cls.user_no_password.save(update_fields=["password", "is_active"])

        cls.user_with_password = UserModel.objects.create_user(
            username="activate-ready",
            email="ready@example.com",
            password="StrongPass123!",
        )
        cls.user_with_password.is_active = True
        cls.user_with_password.save(update_fields=["is_active"])

    def test_activate_redirects_to_password_reset_confirm_when_unusable_password(self) -> None:
        token = TokenService.make_signed(
            namespace=TOKEN_NAMESPACE_ACCOUNTS,
            purpose=TOKEN_PURPOSE_ACTIVATION,
            claims={"user_id": self.user_no_password.id},
        )
        response = self.client.get(reverse("accounts:activate"), {"t": token})
        self.assertEqual(response.status_code, 302)

        refreshed = UserModel.objects.get(pk=self.user_no_password.pk)
        self.assertTrue(refreshed.is_active)
        uidb64 = urlsafe_base64_encode(force_bytes(refreshed.pk))
        expected_token = default_token_generator.make_token(refreshed)
        expected_url = reverse("accounts:password_reset_confirm", kwargs={"uidb64": uidb64, "token": expected_token})
        self.assertEqual(response["Location"], expected_url)

    def test_activate_redirects_to_login_when_already_active(self) -> None:
        token = TokenService.make_signed(
            namespace=TOKEN_NAMESPACE_ACCOUNTS,
            purpose=TOKEN_PURPOSE_ACTIVATION,
            claims={"user_id": self.user_with_password.id},
        )
        response = self.client.get(reverse("accounts:activate"), {"t": token})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("pages:login"))

    def test_activate_invalid_token_returns_400(self) -> None:
        response = self.client.get(reverse("accounts:activate"), {"t": "invalid"})
        self.assertEqual(response.status_code, 400)


class VerifyEmailViewTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = UserModel.objects.create_user(username="verify", email="verify@example.com", password="StrongPass123!")
        cls.profile, _ = StudentProfile.objects.get_or_create(user=cls.user, defaults={"marketing_opt_in": True})

    def test_verify_email_marks_profile_verified(self) -> None:
        token = TokenService.make_signed(
            namespace=TOKEN_NAMESPACE_ACCOUNTS,
            purpose=TOKEN_PURPOSE_VERIFY_EMAIL,
            claims={"user_id": self.user.id},
        )
        url = reverse("messaging:verify-email")
        response = self.client.get(url, {"t": token, "redirect": 0})
        self.assertEqual(response.status_code, 200)
        profile = StudentProfile.objects.get(user=self.user)
        self.assertTrue(profile.email_verified)
        self.assertIsNotNone(profile.email_verified_at)

    def test_verify_email_success_redirect(self) -> None:
        token = TokenService.make_signed(
            namespace=TOKEN_NAMESPACE_ACCOUNTS,
            purpose=TOKEN_PURPOSE_VERIFY_EMAIL,
            claims={"user_id": self.user.id},
        )
        url = reverse("messaging:verify-email")
        response = self.client.get(url, {"t": token})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("pages:verification_success"))

    def test_verify_email_invalid_redirects_to_error(self) -> None:
        url = reverse("messaging:verify-email")
        response = self.client.get(url, {"redirect": 1, "t": "invalid"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("pages:verification_error"))
