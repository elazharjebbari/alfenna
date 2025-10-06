"""Custom DRF throttling classes for the chatbot API."""

from django.conf import settings
from rest_framework.throttling import SimpleRateThrottle


_DEFAULT_RATES = {
    "chat_ip": "30/min",
    "chat_session": "8/min",
    "chat_stream": "20/min",
    "chat_send": "30/min",
}


class ChatThrottleMixin:
    """Mixin providing dynamic rate lookup from settings."""

    def get_rate(self) -> str | None:  # type: ignore[override]
        configured = getattr(settings, "CHATBOT_THROTTLE_RATES", {})
        merged = {**_DEFAULT_RATES, **configured}
        return merged.get(self.scope)


class ChatIPThrottle(ChatThrottleMixin, SimpleRateThrottle):
    scope = "chat_ip"

    def get_cache_key(self, request, view):  # pragma: no cover - simple wrapper
        ident = self.get_ident(request)
        if ident is None:
            return None
        return self.cache_format % {"scope": self.scope, "ident": ident}


class ChatSessionThrottle(ChatThrottleMixin, SimpleRateThrottle):
    scope = "chat_session"

    def get_cache_key(self, request, view):  # pragma: no cover - simple wrapper
        session_id = None
        if request.method in {"POST", "PUT", "PATCH"}:
            session_id = request.data.get("session_id")
        else:
            session_id = request.query_params.get("session")
        if not session_id:
            return None
        return self.cache_format % {"scope": self.scope, "ident": str(session_id)}


class ChatStreamThrottle(ChatThrottleMixin, SimpleRateThrottle):
    scope = "chat_stream"

    def get_cache_key(self, request, view):  # pragma: no cover - simple wrapper
        session_id = request.query_params.get("session")
        if not session_id:
            return None
        return self.cache_format % {"scope": self.scope, "ident": str(session_id)}


class ChatSendThrottle(ChatThrottleMixin, SimpleRateThrottle):
    scope = "chat_send"

    def get_cache_key(self, request, view):  # pragma: no cover - simple wrapper
        session_id = request.data.get("session_id")
        if not session_id:
            return None
        return self.cache_format % {"scope": self.scope, "ident": str(session_id)}
