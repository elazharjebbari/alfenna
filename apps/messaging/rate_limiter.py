from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, MutableMapping, Sequence

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from apps.messaging.models import OutboxEmail

logger = logging.getLogger("apps.messaging.rate_limiter")


@dataclass(slots=True, frozen=True)
class RateLimitDecision:
    user_id: int
    purpose: str
    bucket: int
    sequence: int
    max_per_window: int
    window_seconds: int
    include_failed: bool
    timestamp: int
    allowed: bool

    @property
    def dedup_key(self) -> str:
        return f"user:{self.user_id}:{self.purpose}:{self.bucket}:{self.sequence}"

    @property
    def meter(self) -> str:
        return f"{min(self.sequence, self.max_per_window)}/{self.max_per_window}"

    def to_metadata(self) -> dict[str, int]:
        return {
            "bucket": self.bucket,
            "sequence": self.sequence,
            "max_per_window": self.max_per_window,
            "window_seconds": self.window_seconds,
        }


class EmailRateLimiter:
    """Helper to throttle transactional emails per purpose/user."""

    @classmethod
    def evaluate(cls, *, user_id: int, purpose: str) -> RateLimitDecision:
        config = settings.EMAIL_RATE_LIMIT.get(purpose, {})
        window = max(1, int(config.get("window_seconds", 300)))
        max_per = max(1, int(config.get("max_per_window", 5)))
        include_failed = bool(config.get("include_failed", True))

        now = int(time.time())
        bucket = now // window
        cache_key = f"emailrate:{purpose}:{user_id}:{bucket}"
        sequence = cls._increment(cache_key, window)

        allowed = sequence <= max_per
        if not allowed and not include_failed:
            if cls._has_capacity_after_failures(
                user_id=user_id,
                purpose=purpose,
                bucket=bucket,
                window_seconds=window,
                max_per_window=max_per,
            ):
                allowed = True

        return RateLimitDecision(
            user_id=user_id,
            purpose=purpose,
            bucket=bucket,
            sequence=sequence,
            max_per_window=max_per,
            window_seconds=window,
            include_failed=include_failed,
            timestamp=now,
            allowed=allowed,
        )

    @classmethod
    def record_suppressed(
        cls,
        decision: RateLimitDecision,
        *,
        namespace: str,
        template_slug: str,
        to: Sequence[str] | None,
        metadata: Mapping[str, object] | None = None,
        context: Mapping[str, object] | None = None,
    ) -> None:
        meta: MutableMapping[str, object] = dict(metadata or {})
        rate_payload = decision.to_metadata()
        existing = meta.get("rate_limit")
        if isinstance(existing, dict):
            existing.update(rate_payload)
        else:
            meta["rate_limit"] = rate_payload

        OutboxEmail.objects.create(
            namespace=namespace,
            purpose=decision.purpose,
            dedup_key=f"{decision.dedup_key}:suppressed",
            to=list(to or []),
            locale="fr",
            template_slug=template_slug,
            template_version=0,
            rendered_subject="",
            rendered_html="",
            rendered_text="",
            context={**(context or {}), "reason": "rate_limit"},
            status=OutboxEmail.Status.SUPPRESSED,
            metadata=dict(meta),
        )
        logger.warning(
            "email_rate_limit_suppressed",
            extra={
                "purpose": decision.purpose,
                "user_id": decision.user_id,
                "bucket": decision.bucket,
                "sequence": decision.sequence,
                "max_per_window": decision.max_per_window,
            },
        )

    @staticmethod
    def _increment(cache_key: str, window: int) -> int:
        if cache.add(cache_key, 1, timeout=window):
            return 1
        try:
            value = cache.incr(cache_key)
        except Exception:
            cache.set(cache_key, 1, timeout=window)
            value = 1
        else:
            if hasattr(cache, "touch"):
                try:
                    cache.touch(cache_key, window)
                except Exception:
                    pass
        return int(value)

    @staticmethod
    def _has_capacity_after_failures(
        *,
        user_id: int,
        purpose: str,
        bucket: int,
        window_seconds: int,
        max_per_window: int,
    ) -> bool:
        window_start_ts = bucket * window_seconds
        window_start = datetime.fromtimestamp(window_start_ts, tz=timezone.utc)
        recent = OutboxEmail.objects.filter(
            purpose=purpose,
            metadata__user_id=user_id,
            created_at__gte=window_start,
        )
        successful_like = recent.exclude(
            status__in=[OutboxEmail.Status.FAILED, OutboxEmail.Status.SUPPRESSED]
        ).count()
        return successful_like < max_per_window
