"""Provider router responsible for selecting the active LLM provider."""

from __future__ import annotations

import logging
from typing import Iterable, Mapping

from django.conf import settings

from .base import BaseProvider, ProviderChunk, ProviderError
from .mock import MockProvider
from .openai import OpenAIProvider

log = logging.getLogger("chatbot.service")


class ProviderRouter:
    """Router returning the configured provider implementation."""

    def __init__(self, registry: Mapping[str, BaseProvider] | None = None) -> None:
        self._registry = dict(registry or self._default_registry())

    @staticmethod
    def _default_registry() -> Mapping[str, BaseProvider]:
        return {
            "mock": MockProvider(),
            "openai": OpenAIProvider(),
        }

    def get(self, name: str | None = None) -> BaseProvider:
        provider_name = (name or getattr(settings, "CHATBOT_DEFAULT_PROVIDER", "mock")).lower()
        provider = self._registry.get(provider_name)
        if provider is None:
            log.warning("Unknown provider '%s', falling back to mock", provider_name)
            provider = self._registry["mock"]
        return provider

    def stream(self, *, prompt: str, provider: str | None = None) -> Iterable[ProviderChunk]:
        engine = self.get(provider)
        try:
            yield from engine.stream(prompt=prompt)
        except ProviderError:
            raise
        except Exception as exc:  # pragma: no cover - defensive guard
            log.exception("Provider '%s' raised unexpected error", engine.name)
            raise ProviderError(str(exc))
