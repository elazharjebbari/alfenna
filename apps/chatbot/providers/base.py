"""Base provider definitions for chatbot completions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(slots=True)
class ProviderChunk:
    """Single chunk of streamed provider output."""

    content: str
    is_final: bool = False


class ProviderError(RuntimeError):
    """Raised when the upstream provider fails."""


class BaseProvider:
    """Interface every provider implementation must follow."""

    name = "base"

    def stream(self, *, prompt: str) -> Iterable[ProviderChunk]:  # pragma: no cover - placeholder
        raise NotImplementedError
