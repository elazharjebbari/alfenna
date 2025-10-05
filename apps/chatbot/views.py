"""Views for the chatbot API."""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import StreamingHttpResponse
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.renderers import JSONRenderer

from .models import ChatSession
from .renderers import ServerSentEventRenderer
from .serializers import (
    ChatHistorySerializer,
    ChatSendSerializer,
    ChatStartSerializer,
    ChatStreamSerializer,
    PingSerializer,
)
from .services import ChatService, ConsentService
from .throttling import ChatIPThrottle, ChatSessionThrottle, ChatStreamThrottle, ChatSendThrottle

log_api = logging.getLogger("chatbot.api")
log_stream = logging.getLogger("chatbot.stream")


class ConsentRequiredMixin:
    """Mixin enforcing consent-first policy for chatbot endpoints."""

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        super().initial(request, *args, **kwargs)
        if not ConsentService.has_consent(request):
            raise PermissionDenied(detail="Consent required")


class ChatPingView(ConsentRequiredMixin, APIView):
    """Basic liveness probe for the chatbot API namespace."""

    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = PingSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        result = ChatService.ping()
        payload = {
            "status": "ok",
            "message": result.message,
        }
        return Response(payload)


class ChatConsentView(APIView):
    """Endpoint allowing the visitor to opt-in for chatbot features."""

    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        response = Response({"status": "ok"}, status=status.HTTP_200_OK)
        ConsentService.grant_consent(request=request, response=response)
        response.data = {
            "status": "ok",
            "consent_cookie": settings.CONSENT_COOKIE_NAME,
        }
        log_api.info("chatbot_consent_granted", extra={"ip": request.META.get("REMOTE_ADDR")})
        return response


class ChatStartView(ConsentRequiredMixin, APIView):
    """Create or resume a chat session."""

    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []
    throttle_classes = [ChatIPThrottle]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = ChatStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        session_id = serializer.validated_data.get("session_id")
        session, created = ChatService.start_session(
            request=request,
            session_id=session_id,
        )
        payload = {
            "session_id": str(session.id),
            "session_key": session.session_key,
            "created": created,
        }
        status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        log_api.info(
            "chatbot_session_start",
            extra={
                "session_id": payload["session_id"],
                "session_created": created,
                "ip": request.META.get("REMOTE_ADDR"),
            },
        )
        return Response(payload, status=status_code)


class ChatSendView(ConsentRequiredMixin, APIView):
    """Record a user message within an existing session."""

    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []
    throttle_classes = [ChatIPThrottle, ChatSendThrottle]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = ChatSendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        session_id = serializer.validated_data["session_id"]
        try:
            session = ChatService.get_session(session_id)
        except ChatSession.DoesNotExist as exc:
            raise NotFound(detail="Unknown session") from exc
        try:
            result = ChatService.handle_message(
                session=session,
                text=serializer.validated_data["message"],
                segments=getattr(request, "_segments", None),
                request_id=request.headers.get("X-Request-ID"),
            )
        except DjangoPermissionDenied as exc:
            raise PermissionDenied(detail=str(exc)) from exc
        except ValueError as exc:
            raise ValidationError({"message": str(exc)}) from exc

        payload = {
            "status": "completed" if not result.error else "degraded",
            "session_id": str(result.session.id),
            "user": ChatService.serialize_message(result.user_message),
            "assistant": ChatService.serialize_message(result.assistant_message),
            "chunks": [
                {"content": chunk.content, "final": chunk.is_final}
                for chunk in result.chunks
            ],
            "provider": result.provider,
            "error": result.error,
            "duration_ms": result.duration_ms,
        }
        log_api.info(
            "chatbot_turn",
            extra={
                "session_id": payload["session_id"],
                "provider": result.provider,
                "status": payload["status"],
                "duration_ms": result.duration_ms,
                "error": result.error or "",
            },
        )
        return Response(payload, status=status.HTTP_202_ACCEPTED)


class ChatHistoryView(ConsentRequiredMixin, APIView):
    """Return the persisted messages for a session."""

    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []
    throttle_classes = [ChatIPThrottle, ChatStreamThrottle]

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = ChatHistorySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        session_id = serializer.validated_data["session"]
        limit = serializer.validated_data["limit"]

        try:
            session = ChatService.get_session(session_id)
        except ChatSession.DoesNotExist as exc:
            raise NotFound(detail="Unknown session") from exc

        messages = ChatService.get_history(session=session, limit=limit)
        payload = {
            "session_id": str(session.id),
            "messages": [ChatService.serialize_message(m) for m in messages],
            "count": len(messages),
        }
        return Response(payload)


class ChatStreamView(ConsentRequiredMixin, APIView):
    """Server-sent events stream for assistant messages."""

    authentication_classes: list[Any] = []
    permission_classes: list[Any] = []
    throttle_classes = [ChatIPThrottle, ChatStreamThrottle]
    renderer_classes = [JSONRenderer, ServerSentEventRenderer]

    def get(self, request: Request, *args: Any, **kwargs: Any) -> StreamingHttpResponse:
        serializer = ChatStreamSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        session_id = serializer.validated_data["session"]

        try:
            session = ChatService.get_session(session_id)
        except ChatSession.DoesNotExist as exc:
            raise NotFound(detail="Unknown session") from exc

        accepted_renderer = getattr(request, "accepted_renderer", None)
        if accepted_renderer and not isinstance(accepted_renderer, ServerSentEventRenderer):
            cursor_raw = request.query_params.get("cursor")
            limit_raw = request.query_params.get("limit", "50")
            try:
                limit = max(1, min(int(limit_raw), 100))
            except (TypeError, ValueError):
                limit = 50
            messages = ChatService.get_history(session=session, limit=limit)
            try:
                cursor_val = int(cursor_raw) if cursor_raw is not None else None
            except (TypeError, ValueError):
                cursor_val = None
            if cursor_val is not None:
                messages = [m for m in messages if m.id > cursor_val]
            payload = {
                "session_id": str(session.id),
                "messages": [ChatService.serialize_message(m) for m in messages],
            }
            return Response(payload)

        stream = ChatService.stream_session(session=session)
        response = StreamingHttpResponse(stream, status=status.HTTP_200_OK, content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        log_stream.info("chatbot_stream_start", extra={"session_id": str(session.id)})
        return response
