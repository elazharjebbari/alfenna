from __future__ import annotations

import time
from uuid import uuid4

from django.db import transaction
from django.db.utils import NotSupportedError
from django.utils import timezone

from apps.atelier.analytics.models import (
    AnalyticsEventRaw,
    ComponentStatDaily,
    HeatmapBucketDaily,
)
from apps.atelier.analytics.tasks import rollup_incremental


PAGE_PREFIX = "rollup-exec"
SITE_VERSION = "rollup-exec"
SLOT_ID = "cmp"
COMPONENT_ALIAS = "core/cmp"


def _build_event(event_type: str, *, ts, page_id: str) -> AnalyticsEventRaw:
    payload = {"scroll_pct": 45} if event_type == "scroll" else {}
    return AnalyticsEventRaw(
        event_uuid=uuid4(),
        ts=ts,
        site_version=SITE_VERSION,
        page_id=page_id,
        slot_id=SLOT_ID,
        component_alias=COMPONENT_ALIAS,
        event_type=event_type,
        consent="1",
        ua_hash="exec-ua",
        ip_hash="exec-ip",
        payload=payload,
    )


def run():  # pragma: no cover - executed via runscript
    started = time.time()
    now = timezone.now()
    page_id = f"{PAGE_PREFIX}-{int(now.timestamp())}"
    date_str = now.date().isoformat()

    events = [
        _build_event("view", ts=now, page_id=page_id),
        _build_event("click", ts=now, page_id=page_id),
        _build_event("scroll", ts=now, page_id=page_id),
    ]
    AnalyticsEventRaw.objects.bulk_create(events, ignore_conflicts=True)

    ok = False
    logs: list[str] = []
    try:
        with transaction.atomic():
            rollup_incremental.run(date_str, page_id, SITE_VERSION)
        component = ComponentStatDaily.objects.filter(
            date=now.date(),
            page_id=page_id,
            site_version=SITE_VERSION,
            slot_id=SLOT_ID,
            component_alias=COMPONENT_ALIAS,
        ).first()
        ok = (
            bool(component)
            and component.impressions == 1
            and component.clicks == 1
            and round(component.avg_scroll_pct) == 45
            and component.uu_count == 1
        )
        if component:
            logs.extend(
                [
                    f"impressions={component.impressions}",
                    f"clicks={component.clicks}",
                    f"avg_scroll={round(component.avg_scroll_pct, 2)}",
                    f"uu_count={component.uu_count}",
                ]
            )
    except NotSupportedError as exc:
        logs.append(f"error={exc}")
        ok = False
    finally:
        AnalyticsEventRaw.objects.filter(page_id=page_id, site_version=SITE_VERSION).delete()
        ComponentStatDaily.objects.filter(page_id=page_id, site_version=SITE_VERSION, date=now.date()).delete()
        HeatmapBucketDaily.objects.filter(page_id=page_id, site_version=SITE_VERSION, date=now.date()).delete()

    return {
        "ok": ok,
        "name": __name__,
        "duration": round(time.time() - started, 3),
        "logs": logs,
    }
