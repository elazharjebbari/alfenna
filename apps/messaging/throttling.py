"""Custom throttles for messaging endpoints, mirroring the leads pattern."""
from __future__ import annotations

from rest_framework.throttling import SimpleRateThrottle


class MessagingIPThrottle(SimpleRateThrottle):
    scope = "messaging_ip"

    def get_cache_key(self, request, view):  # pragma: no cover - behaviour mirrored in tests via DRF
        ip = self.get_ident(request)
        purpose = getattr(view, "throttle_purpose", view.__class__.__name__)
        return f"messaging:throttle:ip:{ip}:{purpose}"


class MessagingEmailThrottle(SimpleRateThrottle):
    scope = "messaging_email"

    def get_cache_key(self, request, view):
        email = (request.data.get("email") or "").strip().lower()
        if not email:
            return None
        purpose = getattr(view, "throttle_purpose", view.__class__.__name__)
        return f"messaging:throttle:email:{email}:{purpose}"
