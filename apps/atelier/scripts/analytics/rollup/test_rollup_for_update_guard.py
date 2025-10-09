from __future__ import annotations

import time
from uuid import uuid4

from django.utils import timezone

from apps.atelier.analytics.models import AnalyticsEventRaw
from apps.atelier.analytics.tasks import _component_aggregates_queryset


PAGE_PREFIX = "rollup-guard"
SITE_VERSION = "rollup-guard"
SLOT_ID = "cmp"
COMPONENT_ALIAS = "core/cmp"


def _build_event(event_type: str, *, ts, page_id: str) -> AnalyticsEventRaw:
    return AnalyticsEventRaw(
        event_uuid=uuid4(),
        ts=ts,
        site_version=SITE_VERSION,
        page_id=page_id,
        slot_id=SLOT_ID,
        component_alias=COMPONENT_ALIAS,
        event_type=event_type,
        consent="1",
        ua_hash="guard-ua",
        ip_hash="guard-ip",
        payload={"scroll_pct": 72},
    )


def run():  # pragma: no cover - executed via runscript
    started = time.time()
    now = timezone.now()
    page_id = f"{PAGE_PREFIX}-{int(now.timestamp())}"

    events = [
        _build_event("view", ts=now, page_id=page_id),
        _build_event("click", ts=now, page_id=page_id),
        _build_event("scroll", ts=now, page_id=page_id),
    ]
    AnalyticsEventRaw.objects.bulk_create(events, ignore_conflicts=True)

    sql = str(
        _component_aggregates_queryset(
            day=now.date(), page_id=page_id, site_version=SITE_VERSION
        ).query
    )
    upper_sql = sql.upper()
    has_group_by = "GROUP BY" in upper_sql
    has_for_update = "FOR UPDATE" in upper_sql

    AnalyticsEventRaw.objects.filter(page_id=page_id, site_version=SITE_VERSION).delete()

    return {
        "ok": has_group_by and not has_for_update,
        "name": __name__,
        "duration": round(time.time() - started, 3),
        "logs": [
            f"group_by={has_group_by}",
            f"for_update={has_for_update}",
            sql,
        ],
    }
