"""Serializers for the chatbot REST API."""

from __future__ import annotations

from uuid import UUID

from rest_framework import serializers


class PingSerializer(serializers.Serializer):
    """Serializer used to validate the ping endpoint payload."""

    ping = serializers.CharField(required=False, default="pong")


class ChatStartSerializer(serializers.Serializer):
    session_id = serializers.UUIDField(required=False)
    locale = serializers.CharField(required=False, max_length=8)


class ChatSendSerializer(serializers.Serializer):
    session_id = serializers.UUIDField()
    message = serializers.CharField(allow_blank=False, max_length=4000)

    def validate_message(self, value: str) -> str:
        text = value.strip()
        if not text:
            raise serializers.ValidationError("Message cannot be empty")
        return text


class ChatHistorySerializer(serializers.Serializer):
    session = serializers.UUIDField()
    limit = serializers.IntegerField(required=False, min_value=1, max_value=50, default=20)


class ChatMessageSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    role = serializers.CharField()
    content = serializers.CharField()
    created_at = serializers.DateTimeField()

    @classmethod
    def from_instance(cls, message) -> dict[str, str]:  # pragma: no cover - simple helper
        return {
            "id": message.id,
            "role": message.role,
            "content": message.content,
            "created_at": message.created_at.isoformat(),
        }


class ChatStreamSerializer(serializers.Serializer):
    session = serializers.UUIDField()
