from __future__ import annotations

from urllib.parse import urlencode

from django.conf import settings
from django.urls import reverse

from apps.messaging.constants import (
    EMAIL_VERIFICATION_TTL_SECONDS,
    TOKEN_NAMESPACE_ACCOUNTS,
    TOKEN_PURPOSE_VERIFY_EMAIL,
)
from apps.messaging.rate_limiter import EmailRateLimiter
from apps.messaging.services import EmailService
from apps.messaging.tokens import TokenService
from apps.messaging.utils import secure_base_url


def enqueue_email_verification(user) -> None:
    if not getattr(user, "email", None):
        return

    token = TokenService.make_signed(
        namespace=TOKEN_NAMESPACE_ACCOUNTS,
        purpose=TOKEN_PURPOSE_VERIFY_EMAIL,
        claims={"user_id": user.id},
    )
    verification_path = reverse("messaging:verify-email")
    verification_url = f"{secure_base_url()}{verification_path}?{urlencode({'t': token})}"

    first_name = getattr(user, "first_name", "") or getattr(user, "username", "") or user.email
    site_name = getattr(settings, "SITE_NAME", "Lumière Academy")
    support_email = getattr(settings, "SUPPORT_EMAIL", settings.DEFAULT_FROM_EMAIL)
    decision = EmailRateLimiter.evaluate(user_id=user.id, purpose="email_verification")
    if not decision.allowed:
        EmailRateLimiter.record_suppressed(
            decision,
            namespace="accounts",
            template_slug="accounts/verify",
            to=[user.email],
            metadata={"user_id": user.id},
            context={"user_first_name": first_name},
        )
        return

    EmailService.compose_and_enqueue(
        namespace="accounts",
        purpose="email_verification",
        template_slug="accounts/verify",
        to=[user.email],
        user=user,
        dedup_key=decision.dedup_key,
        context={
            "user_first_name": first_name,
            "verification_url": verification_url,
            "verification_ttl_hours": EMAIL_VERIFICATION_TTL_SECONDS // 3600,
            "site_name": site_name,
            "support_email": support_email,
        },
        metadata={
            "user_id": user.id,
            "rate_limit": decision.to_metadata(),
        },
    )
