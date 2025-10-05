"""Service layer entry points for the chatbot domain."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

from django.apps import apps
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.utils import timezone

from apps.marketing.helpers import has_marketing_consent

from . import metrics as metrics_module
from .models import ChatMessage, ChatSession, ProviderCall
from .providers import ProviderChunk, ProviderError, ProviderRouter

log = logging.getLogger("chatbot.service")


@dataclass(slots=True)
class ChatServiceResult:
    message: str


@dataclass(slots=True)
class ChatServiceResponse:
    """Structured response after handling a chat turn."""

    session: ChatSession
    user_message: ChatMessage
    assistant_message: ChatMessage
    chunks: List[ProviderChunk]
    provider: str
    error: Optional[str]
    duration_ms: int


class RedactionService:
    """Utility to redact obvious PII from provider output."""

    EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    PHONE_PATTERN = re.compile(r"\b\d{6,}\b")

    @classmethod
    def redact(cls, text: str) -> str:
        if not text:
            return text
        redacted = cls.EMAIL_PATTERN.sub("[redacted_email]", text)
        redacted = cls.PHONE_PATTERN.sub("[redacted_number]", redacted)
        return redacted


class ConsentService:
    """Helpers around the consent cookie and audit trail."""

    TRUE_VALUE = "yes"

    @classmethod
    def has_consent(cls, request: HttpRequest) -> bool:
        segments = getattr(request, "_segments", None)
        consent_flag = getattr(segments, "consent", None) if segments else None
        if consent_flag == "Y":
            return True
        return has_marketing_consent(request)

    @classmethod
    def grant_consent(cls, *, request: HttpRequest, response: HttpResponse) -> None:
        """Persist the consent cookie and audit the event if possible."""

        cls._set_cookie(response)
        try:
            cls._record_event(request=request, value="Y")
        except Exception:  # pragma: no cover - audit failures must not break flow
            log.exception("Unable to record consent event")

    @classmethod
    def _set_cookie(cls, response: HttpResponse) -> None:
        cookie_name = getattr(settings, "CONSENT_COOKIE_NAME", "cookie_consent_marketing")
        secure = getattr(settings, "SESSION_COOKIE_SECURE", False)
        response.set_cookie(
            cookie_name,
            cls.TRUE_VALUE,
            max_age=15552000,  # 6 months
            samesite="Lax",
            secure=secure,
        )

    @classmethod
    def _record_event(cls, *, request: HttpRequest, value: str) -> None:
        ConsentEvent = cls._get_consent_event_model()
        if ConsentEvent is None:
            return
        ConsentEvent.objects.create(  # type: ignore[attr-defined]
            session=None,
            user=cls._get_user(request),
            value=value,
            ip=cls._mask_ip(request),
            user_agent=cls._truncate_user_agent(request),
        )

    @staticmethod
    def _mask_ip(request: HttpRequest) -> str:
        ip = request.META.get("REMOTE_ADDR", "")
        if not ip:
            return ""
        parts = ip.split(".")
        if len(parts) == 4:
            parts[-1] = "0"
            return ".".join(parts)
        return ip

    @staticmethod
    def _truncate_user_agent(request: HttpRequest) -> str:
        ua = request.META.get("HTTP_USER_AGENT", "") or ""
        return ua[:255]

    @staticmethod
    def _get_consent_event_model() -> Optional[type]:
        try:
            return apps.get_model("chatbot", "ConsentEvent")
        except LookupError:
            return None

    @staticmethod
    def _get_user(request: HttpRequest) -> Optional[object]:
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            return user
        return None


class ChatService:
    """Facade for chatbot operations."""

    @classmethod
    def ping(cls) -> ChatServiceResult:
        return ChatServiceResult(message="pong")

    @classmethod
    def start_session(
        cls,
        *,
        request: HttpRequest,
        session_id: Optional[uuid.UUID] = None,
    ) -> Tuple[ChatSession, bool]:
        """Load an existing session or create a new one."""

        if session_id is not None:
            try:
                session = ChatSession.objects.get(pk=session_id)
                return session, False
            except ChatSession.DoesNotExist:
                pass

        user = ConsentService._get_user(request)
        segments = getattr(request, "_segments", None)
        locale = getattr(segments, "lang", "fr") if segments else "fr"
        consent_snapshot = getattr(segments, "consent", "N") if segments else "N"

        session = ChatSession.objects.create(
            session_key=uuid.uuid4().hex,
            consent_snapshot=consent_snapshot,
            locale=locale,
            user=user,
            last_activity=timezone.now(),
        )
        metrics_module.record_session_started(str(session.id), locale=locale)
        return session, True

    @classmethod
    def get_session(cls, session_id: uuid.UUID) -> ChatSession:
        return ChatSession.objects.get(pk=session_id)

    @classmethod
    def add_user_message(cls, *, session: ChatSession, content: str) -> ChatMessage:
        text = content.strip()
        if not text:
            raise ValueError("Message content cannot be blank")

        with transaction.atomic():
            message = ChatMessage.objects.create(
                session=session,
                role=ChatMessage.ROLE_USER,
                content=text,
            )
            ChatSession.objects.filter(pk=session.pk).update(last_activity=timezone.now())
        session.refresh_from_db(fields=["last_activity"])
        return message

    @classmethod
    def get_history(cls, *, session: ChatSession, limit: int = 20) -> List[ChatMessage]:
        qs = session.messages.order_by("-created_at")[:limit]
        messages = list(qs)
        return list(reversed(messages))

    @staticmethod
    def serialize_message(message: ChatMessage) -> dict[str, str]:
        return {
            "id": message.id,
            "role": message.role,
            "content": message.content,
            "created_at": message.created_at.isoformat(),
        }

    @classmethod
    def handle_message(
        cls,
        *,
        session: ChatSession,
        text: str,
        segments: object | None,
        request_id: str | None = None,
    ) -> ChatServiceResponse:
        """Process a user message and return the assistant reply."""

        consent_flag = getattr(segments, "consent", "N") if segments else "N"
        if consent_flag != "Y":
            raise PermissionDenied("Consent required")

        user_message = cls.add_user_message(session=session, content=text)
        provider_name = getattr(settings, "CHATBOT_DEFAULT_PROVIDER", "mock")
        provider_in_use = provider_name
        circuit_triggered = False
        if cls._is_circuit_open(provider_name):
            provider_in_use = "mock"
            circuit_triggered = True

        router = ProviderRouter()
        request_hash = cls._hash_prompt(text)
        call = ProviderCall.objects.create(
            session=session,
            provider=provider_in_use,
            model=getattr(settings, "CHATBOT_MODEL_NAME", provider_in_use),
            status=ProviderCall.STATUS_PENDING,
            request_hash=request_hash,
        )

        start = time.perf_counter()
        chunks: List[ProviderChunk] = []
        error: Optional[str] = "circuit_open" if circuit_triggered and provider_in_use != provider_name else None

        try:
            for chunk in router.stream(prompt=text, provider=provider_in_use):
                sanitized = RedactionService.redact(chunk.content)
                chunks.append(ProviderChunk(content=sanitized, is_final=chunk.is_final))
            content = "".join(piece.content for piece in chunks).strip()
            if not content:
                content = settings.CHATBOT_FALLBACK_MESSAGE
            assistant_message = ChatMessage.objects.create(
                session=session,
                role=ChatMessage.ROLE_ASSISTANT,
                content=content,
                tokens_in=cls._estimate_tokens(text),
                tokens_out=cls._estimate_tokens(content),
                latency_ms=cls._elapsed_ms(start),
            )
            call.status = ProviderCall.STATUS_SUCCESS
            if provider_in_use == provider_name and not circuit_triggered:
                cls._record_provider_success(provider_name)
        except ProviderError as exc:
            error = str(exc)
            fallback = settings.CHATBOT_FALLBACK_MESSAGE
            chunks = [ProviderChunk(content=fallback, is_final=True)]
            assistant_message = ChatMessage.objects.create(
                session=session,
                role=ChatMessage.ROLE_ASSISTANT,
                content=fallback,
                tokens_in=cls._estimate_tokens(text),
                tokens_out=cls._estimate_tokens(fallback),
                latency_ms=cls._elapsed_ms(start),
            )
            call.status = ProviderCall.STATUS_ERROR
            cls._record_provider_failure(provider_name)
        finally:
            call.duration_ms = cls._elapsed_ms(start)
            call.save(update_fields=["status", "duration_ms"])

        ChatSession.objects.filter(pk=session.pk).update(last_activity=timezone.now())
        session.refresh_from_db(fields=["last_activity"])

        metrics_module.record_turn_completed(
            session_id=str(session.id),
            provider=provider_in_use,
            duration_ms=call.duration_ms or 0,
            error=error,
        )

        return ChatServiceResponse(
            session=session,
            user_message=user_message,
            assistant_message=assistant_message,
            chunks=chunks,
            provider=provider_in_use,
            error=error,
            duration_ms=call.duration_ms or 0,
        )

    @classmethod
    def stream_session(cls, *, session: ChatSession, limit: int = 50) -> Iterable[str]:
        messages = cls.get_history(session=session, limit=limit)
        yield cls._format_event("init", {"session_id": str(session.id), "count": len(messages)})
        for message in messages:
            yield cls._format_event("message", cls.serialize_message(message))
        yield cls._format_event("done", {"session_id": str(session.id)})
        yield cls._format_event("heartbeat", {"session_id": str(session.id)})

    @staticmethod
    def _format_event(event: str, data: dict[str, object]) -> str:
        payload = json.dumps(data)
        return f"event: {event}\ndata: {payload}\n\n"

    @staticmethod
    def _elapsed_ms(start: float) -> int:
        return int((time.perf_counter() - start) * 1000)

    @staticmethod
    def _hash_prompt(prompt: str) -> str:
        digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        return digest[:64]

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        if not text:
            return 0
        return max(len(text.split()), 1)

    @classmethod
    def _provider_cache_key(cls, provider: str) -> str:
        return f"chatbot:circuit:{provider}"

    @classmethod
    def _record_provider_success(cls, provider: str) -> None:
        if provider == "mock":
            return
        cache.delete(cls._provider_cache_key(provider))

    @classmethod
    def _record_provider_failure(cls, provider: str) -> None:
        if provider == "mock":
            return
        key = cls._provider_cache_key(provider)
        data = cache.get(key, {"count": 0, "opened_at": None})
        data["count"] = int(data.get("count", 0)) + 1
        if data["count"] >= cls._circuit_threshold():
            data["opened_at"] = time.time()
        cache.set(key, data, cls._circuit_ttl())

    @classmethod
    def _is_circuit_open(cls, provider: str) -> bool:
        if provider == "mock":
            return False
        key = cls._provider_cache_key(provider)
        data = cache.get(key)
        if not data:
            return False
        opened_at = data.get("opened_at")
        if not opened_at:
            return False
        if time.time() - float(opened_at) > cls._circuit_ttl():
            cache.delete(key)
            return False
        return True

    @staticmethod
    def _circuit_threshold() -> int:
        return getattr(settings, "CHATBOT_PROVIDER_FAILURE_THRESHOLD", 3)

    @staticmethod
    def _circuit_ttl() -> int:
        return getattr(settings, "CHATBOT_PROVIDER_CIRCUIT_TTL", 300)
