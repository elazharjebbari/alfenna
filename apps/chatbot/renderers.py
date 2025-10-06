"""Renderer definitions for chatbot endpoints."""

from rest_framework.renderers import BaseRenderer


class ServerSentEventRenderer(BaseRenderer):
    media_type = "text/event-stream"
    format = "sse"
    charset = "utf-8"

    def render(self, data, accepted_media_type=None, renderer_context=None):  # pragma: no cover - passthrough
        return data
