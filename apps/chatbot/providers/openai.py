"""OpenAI provider placeholder implementation."""

from __future__ import annotations

from typing import Iterable

from .base import BaseProvider, ProviderChunk


class OpenAIProvider(BaseProvider):
    """Simplified provider stub.

    The concrete streaming implementation lands in later steps.
    """

    name = "openai"

    def stream(self, *, prompt: str) -> Iterable[ProviderChunk]:  # pragma: no cover - placeholder
        yield ProviderChunk(content=f"echo: {prompt}", is_final=True)
