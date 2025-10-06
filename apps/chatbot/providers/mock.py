"""Mock provider used for local development and tests."""

from __future__ import annotations

from typing import Iterable

from .base import BaseProvider, ProviderChunk


class MockProvider(BaseProvider):
    """Simple provider that echoes the prompt with a canned prefix."""

    name = "mock"

    def __init__(self, *, prefix: str = "Assistant") -> None:
        self.prefix = prefix

    def stream(self, *, prompt: str) -> Iterable[ProviderChunk]:
        yield ProviderChunk(content=f"{self.prefix}: {prompt}", is_final=True)
