from __future__ import annotations

from urllib.parse import urlencode
from uuid import uuid4

from django.conf import settings
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils import timezone
from django.urls import reverse

from apps.messaging.rate_limiter import EmailRateLimiter
from apps.messaging.services import EmailService
from apps.messaging.utils import secure_base_url


class OutboxPasswordResetForm(PasswordResetForm):
    def save(
        self,
        domain_override=None,
        subject_template_name=None,
        email_template_name=None,
        use_https=False,
        token_generator=default_token_generator,
        from_email=None,
        request=None,
        html_email_template_name=None,
        extra_email_context=None,
        next_url=None,
    ):
        if request is None:
            raise ValueError("request is required to build reset URL")

        email = self.cleaned_data["email"]
        site_name = getattr(settings, "SITE_NAME", "Lumière Academy")
        support_email = getattr(settings, "SUPPORT_EMAIL", settings.DEFAULT_FROM_EMAIL)
        ttl_minutes = getattr(settings, "PASSWORD_RESET_TIMEOUT", 3600) // 60

        self.reset_flows: list[dict] = []

        for user in self.get_users(email):
            flow_id = uuid4().hex
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = token_generator.make_token(user)
            path = reverse("accounts:password_reset_confirm", kwargs={"uidb64": uid, "token": token})
            reset_url = f"{secure_base_url()}{path}"
            if next_url:
                reset_url = f"{reset_url}?{urlencode({'next': next_url})}"
            first_name = getattr(user, "first_name", "") or getattr(user, "username", "") or user.email

            decision = EmailRateLimiter.evaluate(user_id=user.id, purpose="password_reset")
            if not decision.allowed:
                EmailRateLimiter.record_suppressed(
                    decision,
                    namespace="accounts",
                    template_slug="accounts/reset",
                    to=[user.email],
                    metadata={"user_id": user.id},
                    context={"reset_url": reset_url},
                )
                continue

            EmailService.compose_and_enqueue(
                namespace="accounts",
                purpose="password_reset",
                template_slug="accounts/reset",
                to=[user.email],
                dedup_key=decision.dedup_key,
                context={
                    "user_first_name": first_name,
                    "reset_url": reset_url,
                    "reset_ttl_minutes": ttl_minutes,
                    "support_email": support_email,
                    "site_name": site_name,
                },
                metadata={
                    "user_id": user.id,
                    "rate_limit": decision.to_metadata(),
                    "flow_id": flow_id,
                },
                flow_id=flow_id,
            )
            self.reset_flows.append(
                {
                    "flow_id": flow_id,
                    "state": "queued",
                    "created_at": timezone.now().isoformat(),
                }
            )

        if not self.reset_flows:
            flow_id = uuid4().hex
            self.reset_flows.append(
                {
                    "flow_id": flow_id,
                    "state": "noop",
                    "created_at": timezone.now().isoformat(),
                }
            )

    @property
    def primary_flow(self) -> dict:
        if getattr(self, "reset_flows", None):
            return self.reset_flows[0]
        return {"flow_id": "", "state": "noop"}
