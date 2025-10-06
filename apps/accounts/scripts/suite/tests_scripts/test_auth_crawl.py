from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.test import Client
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.accounts.models import StudentProfile
from apps.common.runscript_harness import binary_harness
from apps.messaging.constants import (
    TOKEN_NAMESPACE_ACCOUNTS,
    TOKEN_PURPOSE_ACTIVATION,
    TOKEN_PURPOSE_VERIFY_EMAIL,
)
from apps.messaging.models import OutboxEmail
from apps.messaging.tokens import TokenService


UserModel = get_user_model()


@binary_harness
def run(*args):
    print("== accounts_auth_crawl: start ==")

    client = Client()

    login_page = client.get(reverse("accounts:login"))
    assert login_page.status_code == 200, "Login page unavailable"
    login_html = login_page.content.decode("utf-8", errors="ignore")
    assert "Mot de passe oublié" in login_html, "Login page missing reset link"
    assert "Créer un compte" in login_html, "Login page missing register link"

    OutboxEmail.objects.filter(purpose__in=["email_verification", "password_reset"]).delete()

    suffix = uuid.uuid4().hex[:8]
    email = f"crawl-{suffix}@example.com"
    register_payload = {
        "full_name": "Crawler User",
        "email": email,
        "password1": "StrongPass123!",
        "password2": "StrongPass123!",
        "marketing_opt_in": "on",
    }

    register_response = client.post(
        reverse("accounts:register"),
        data=register_payload,
        follow=False,
    )
    assert register_response.status_code in (302, 303), "Register should redirect"
    check_email_url = reverse("pages:check_email")
    assert register_response["Location"].startswith(check_email_url), "Register should redirect to check email"

    user = UserModel.objects.get(email=email)
    StudentProfile.objects.get(user=user)

    verification_emails = OutboxEmail.objects.filter(purpose="email_verification")
    assert verification_emails.count() == 1, "Verification email missing"

    reset_response = client.post(
        reverse("accounts:password_reset"),
        data={"email": email},
        follow=False,
    )
    assert reset_response.status_code in (302, 303), "Password reset should redirect"
    assert reset_response["Location"].startswith(reverse("accounts:password_reset_done")), "Reset should redirect to done"

    reset_outbox = OutboxEmail.objects.filter(purpose="password_reset")
    assert reset_outbox.count() == 1, "Password reset email missing"

    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    confirm_url = reverse("accounts:password_reset_confirm", kwargs={"uidb64": uidb64, "token": token})

    alias_redirect = client.get(f"/mot-de-passe-oublie/definir/{uidb64}/{token}/")
    assert alias_redirect.status_code == 301, "French alias should redirect"
    assert alias_redirect["Location"].endswith(confirm_url), "Alias must keep parameters"

    fallback_redirect = client.get("/accounts/reset/confirm/", {"uid": uidb64, "token": token, "next": "/cours/"})
    assert fallback_redirect.status_code == 302, "Querystring fallback should redirect"
    assert fallback_redirect["Location"] == f"{confirm_url}?next=%2Fcours%2F", "Fallback must preserve next"

    confirm_page = client.get(confirm_url)
    if confirm_page.status_code in (301, 302, 303):
        redirected_url = confirm_page["Location"]
        assert redirected_url.endswith("/set-password/"), "Confirm redirect should target set-password"
        confirm_page = client.get(redirected_url)
    assert confirm_page.status_code == 200, "Confirm page should load"

    verify_token = TokenService.make_signed(
        namespace=TOKEN_NAMESPACE_ACCOUNTS,
        purpose=TOKEN_PURPOSE_VERIFY_EMAIL,
        claims={"user_id": user.id},
    )
    verify_response = client.get(reverse("messaging:verify-email"), {"t": verify_token})
    assert verify_response.status_code == 302, "Verify email should redirect"
    assert verify_response["Location"].endswith(reverse("pages:verification_success")), "Verify email should land on success"

    invalid_verify = client.get(reverse("messaging:verify-email"), {"t": "invalid"})
    assert invalid_verify.status_code == 302, "Invalid verify should redirect"
    assert invalid_verify["Location"].endswith(reverse("pages:verification_error")), "Invalid verify should go to error"

    activation_target = UserModel.objects.create_user(
        username=f"pending-{suffix}",
        email=f"pending-{suffix}@example.com",
    )
    activation_target.set_unusable_password()
    activation_target.is_active = False
    activation_target.save(update_fields=["password", "is_active"])
    StudentProfile.objects.get_or_create(user=activation_target)

    activation_token = TokenService.make_signed(
        namespace=TOKEN_NAMESPACE_ACCOUNTS,
        purpose=TOKEN_PURPOSE_ACTIVATION,
        claims={"user_id": activation_target.id},
    )
    activation_response = client.get(reverse("accounts:activate"), {"t": activation_token})
    assert activation_response.status_code == 302, "Activation should redirect"
    activation_target.refresh_from_db()
    location = activation_response["Location"]
    expected_uid = urlsafe_base64_encode(force_bytes(activation_target.pk))
    assert location.startswith(f"/accounts/password-reset/confirm/{expected_uid}/"), "Activation must target confirm"
    actual_token = location.rstrip("/").split("/")[-1]
    assert default_token_generator.check_token(activation_target, actual_token), "Activation token should be valid"

    print("== accounts_auth_crawl: OK ✅ ==")
