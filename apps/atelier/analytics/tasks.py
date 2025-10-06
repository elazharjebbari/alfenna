"""Celery tasks for analytics ingestion and rollups."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
import hashlib
import logging
from typing import Dict, List, Tuple

from celery import shared_task
from django.db import transaction
from django.db.models import Avg, Count, Q, FloatField
from django.db.models.functions import Cast
from django.db.models.fields.json import KeyTextTransform
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import AnalyticsEventRaw, ComponentStatDaily, HeatmapBucketDaily


log = logging.getLogger("apps.atelier.analytics.tasks")

_EVENT_TYPES = {"view", "click", "scroll", "heatmap"}


def _stable_hash(value: str | None) -> str:
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _ensure_datetime(value: str | datetime | None) -> datetime:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        parsed = parse_datetime(value)
        if parsed is None:
            dt = timezone.now()
        else:
            dt = parsed
    else:
        dt = timezone.now()
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_default_timezone())
    return dt


def _normalize_event(event: Dict, ua_hash: str, ip_hash: str) -> AnalyticsEventRaw | None:
    event_type = (event.get("event_type") or "").lower()
    if event_type not in _EVENT_TYPES:
        return None
    ts = _ensure_datetime(event.get("ts"))
    payload = event.get("payload") or {}
    return AnalyticsEventRaw(
        event_uuid=event.get("event_uuid"),
        ts=ts,
        request_id=(event.get("request_id") or "")[:64],
        site_version=(event.get("site_version") or "")[:32],
        page_id=(event.get("page_id") or "")[:128],
        slot_id=(event.get("slot_id") or "")[:128],
        component_alias=(event.get("component_alias") or "")[:128],
        event_type=event_type,
        user_id=(event.get("user_id") or "")[:64],
        consent=(event.get("consent") or "")[:1],
        lang=(event.get("lang") or "")[:8],
        device=(event.get("device") or "")[:8],
        path=(event.get("path") or "")[:512],
        referer=(event.get("referer") or "")[:512],
        ua_hash=ua_hash,
        ip_hash=ip_hash,
        payload=payload,
    )


@shared_task(queue="analytics", autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def persist_raw(events: List[Dict], meta: Dict | None = None) -> int:
    """Persist analytics events and trigger incremental rollups."""
    if not events:
        return 0

    meta = meta or {}
    ua_hash = _stable_hash(meta.get("user_agent"))
    ip_hash = _stable_hash(meta.get("ip"))

    normalized: List[AnalyticsEventRaw] = []
    rollup_targets: set[Tuple[str, str, str]] = set()
    for event in events:
        normalized_event = _normalize_event(event, ua_hash=ua_hash, ip_hash=ip_hash)
        if not normalized_event or not normalized_event.event_uuid:
            continue
        normalized.append(normalized_event)
        rollup_targets.add((
            normalized_event.ts.date().isoformat(),
            normalized_event.page_id,
            normalized_event.site_version,
        ))

    if not normalized:
        return 0

    created = AnalyticsEventRaw.objects.bulk_create(normalized, ignore_conflicts=True, batch_size=500)
    log.debug("persist_raw stored=%s events targets=%s", len(created), len(rollup_targets))

    for date_str, page_id, site_version in rollup_targets:
        if not page_id:
            continue
        rollup_incremental.delay(date_str, page_id, site_version)

    return len(normalized)


def _update_component_daily(day: date, page_id: str, site_version: str, qs) -> None:
    scroll_value = Cast(
        KeyTextTransform("scroll_pct", "payload"),
        FloatField(),
    )

    aggregates = qs.values("slot_id", "component_alias").annotate(
        impressions=Count("id", filter=Q(event_type="view")),
        clicks=Count("id", filter=Q(event_type="click")),
        avg_scroll_pct=Avg(
            scroll_value,
            filter=Q(event_type="scroll")
            & ~Q(payload__scroll_pct=None)
            & ~Q(payload__scroll_pct=""),
        ),
    )

    visitor_map: Dict[Tuple[str, str], set[str]] = defaultdict(set)
    visitor_rows = qs.values("slot_id", "component_alias", "ua_hash", "ip_hash")
    for row in visitor_rows:
        slot = (row.get("slot_id") or "", row.get("component_alias") or "")
        ua = row.get("ua_hash") or ""
        ip = row.get("ip_hash") or ""
        if not ua and not ip:
            continue
        visitor_map[slot].add(f"{ua}:{ip}")

    seen_keys: set[Tuple[str, str]] = set()
    for agg in aggregates:
        slot_id = agg.get("slot_id") or ""
        component_alias = agg.get("component_alias") or ""
        key = (slot_id, component_alias)
        seen_keys.add(key)
        defaults = {
            "impressions": int(agg.get("impressions") or 0),
            "clicks": int(agg.get("clicks") or 0),
            "avg_scroll_pct": float(agg.get("avg_scroll_pct") or 0.0),
            "uu_count": len(visitor_map.get(key, set())),
        }
        ComponentStatDaily.objects.update_or_create(
            date=day,
            site_version=site_version,
            page_id=page_id,
            slot_id=slot_id,
            component_alias=component_alias,
            defaults=defaults,
        )

    existing = ComponentStatDaily.objects.filter(
        date=day,
        site_version=site_version,
        page_id=page_id,
    )
    for obj in existing:
        key = (obj.slot_id or "", obj.component_alias or "")
        if key not in seen_keys:
            obj.delete()


def _bucket(value: float | None) -> int | None:
    if value is None:
        return None
    try:
        val = float(value)
    except (TypeError, ValueError):
        return None
    if val < 0:
        val = 0.0
    if val > 1:
        val = 1.0
    bucket = int(val * 100)
    if bucket > 99:
        bucket = 99
    return bucket


def _update_heatmap(day: date, page_id: str, site_version: str, qs) -> None:
    heatmap_rows_qs = qs.filter(event_type="heatmap").values("device", "payload__x", "payload__y")
    heatmap_rows = list(heatmap_rows_qs)
    if not heatmap_rows:
        HeatmapBucketDaily.objects.filter(
            date=day,
            page_id=page_id,
            site_version=site_version,
        ).delete()
        return

    counts: Dict[Tuple[str, int, int], int] = defaultdict(int)
    for row in heatmap_rows:
        bx = _bucket(row.get("payload__x"))
        by = _bucket(row.get("payload__y"))
        if bx is None or by is None:
            continue
        device = (row.get("device") or "").strip()[:8]
        counts[(device, bx, by)] += 1

    existing = {
        (obj.device or "", obj.bucket_x, obj.bucket_y): obj
        for obj in HeatmapBucketDaily.objects.filter(
            date=day,
            page_id=page_id,
            site_version=site_version,
        )
    }

    seen_keys = set()
    for (device, bx, by), hits in counts.items():
        seen_keys.add((device, bx, by))
        HeatmapBucketDaily.objects.update_or_create(
            date=day,
            site_version=site_version,
            page_id=page_id,
            device=device,
            bucket_x=bx,
            bucket_y=by,
            defaults={"hits": hits},
        )

    for key, obj in existing.items():
        if key not in seen_keys:
            obj.delete()


@shared_task(queue="analytics")
def rollup_incremental(date_str: str, page_id: str, site_version: str) -> None:
    day = date.fromisoformat(date_str)
    with transaction.atomic():
        qs = AnalyticsEventRaw.objects.select_for_update().filter(
            ts__date=day,
            page_id=page_id,
            site_version=site_version,
        )
        if not qs.exists():
            ComponentStatDaily.objects.filter(
                date=day,
                page_id=page_id,
                site_version=site_version,
            ).delete()
            HeatmapBucketDaily.objects.filter(
                date=day,
                page_id=page_id,
                site_version=site_version,
            ).delete()
            return
        _update_component_daily(day, page_id, site_version, qs)
        _update_heatmap(day, page_id, site_version, qs)
        log.debug(
            "rollup_incremental completed date=%s page=%s site=%s", date_str, page_id, site_version
        )


__all__ = ["persist_raw", "rollup_incremental"]
