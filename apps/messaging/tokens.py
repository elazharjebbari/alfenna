"""Signed token utilities for messaging flows."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict

from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.utils import timezone

from .exceptions import TokenExpiredError, TokenInvalidError


@dataclass(frozen=True)
class TokenPayload:
    namespace: str
    purpose: str
    claims: Dict[str, Any]
    issued_at: datetime


class TokenService:
    """Generate and validate signed tokens with TTL semantics."""

    SALT_PREFIX = "apps.messaging.tokens"

    @classmethod
    def _signer(cls, namespace: str, purpose: str) -> TimestampSigner:
        salt = f"{cls.SALT_PREFIX}:{namespace}:{purpose}"
        return TimestampSigner(salt=salt)

    @classmethod
    def make_signed(
        cls,
        *,
        namespace: str,
        purpose: str,
        claims: Dict[str, Any],
    ) -> str:
        payload = {
            "claims": claims,
            "issued_at": timezone.now().isoformat(),
        }
        signer = cls._signer(namespace, purpose)
        serialized = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        return signer.sign(serialized)

    @classmethod
    def sign(
        cls,
        *,
        namespace: str,
        purpose: str,
        claims: Dict[str, Any],
        ttl_seconds: int | None = None,
    ) -> str:
        # ``ttl_seconds`` is accepted for ergonomics even though signing does
        # not embed the TTL. Expiry enforcement happens when reading the token.
        del ttl_seconds  # not used during signing; kept for API symmetry
        return cls.make_signed(namespace=namespace, purpose=purpose, claims=claims)

    @classmethod
    def read_signed(
        cls,
        token: str,
        *,
        namespace: str,
        purpose: str,
        ttl_seconds: int,
    ) -> TokenPayload:
        signer = cls._signer(namespace, purpose)
        try:
            raw = signer.unsign(token, max_age=ttl_seconds)
        except SignatureExpired as exc:  # pragma: no cover - defensive
            raise TokenExpiredError("Token expired") from exc
        except BadSignature as exc:  # pragma: no cover - defensive
            raise TokenInvalidError("Token invalid") from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise TokenInvalidError("Malformed token payload") from exc

        issued_at_raw = data.get("issued_at")
        if not issued_at_raw:
            raise TokenInvalidError("Missing issued_at claim")
        try:
            issued_at = datetime.fromisoformat(issued_at_raw)
        except ValueError as exc:  # pragma: no cover - defensive
            raise TokenInvalidError("Invalid issued_at format") from exc

        claims = data.get("claims")
        if not isinstance(claims, dict):
            raise TokenInvalidError("Claims must be a JSON object")

        return TokenPayload(namespace=namespace, purpose=purpose, claims=claims, issued_at=issued_at)
