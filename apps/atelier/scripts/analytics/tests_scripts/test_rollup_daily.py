from __future__ import annotations

import time
from unittest.mock import patch
from uuid import uuid4

from django.utils import timezone

from apps.atelier.analytics import tasks
from apps.atelier.analytics.models import AnalyticsEventRaw, ComponentStatDaily


def run():
    started = time.time()
    AnalyticsEventRaw.objects.all().delete()
    ComponentStatDaily.objects.all().delete()

    now = timezone.now()
    base_ts = now.isoformat()
    events = [
        {
            "event_uuid": str(uuid4()),
            "event_type": "view",
            "page_id": "home",
            "slot_id": "hero",
            "component_alias": "core/hero",
            "ts": base_ts,
        },
        {
            "event_uuid": str(uuid4()),
            "event_type": "click",
            "page_id": "home",
            "slot_id": "hero",
            "component_alias": "core/hero",
            "ts": base_ts,
        },
        {
            "event_uuid": str(uuid4()),
            "event_type": "scroll",
            "page_id": "home",
            "slot_id": "hero",
            "component_alias": "core/hero",
            "payload": {"scroll_pct": 80},
            "ts": base_ts,
        },
    ]

    target_date = now.date()

    with patch.object(tasks.rollup_incremental, "delay", side_effect=lambda *args, **kwargs: tasks.rollup_incremental.run(*args, **kwargs)):
        tasks.persist_raw.run(events, meta={"user_agent": "pytest", "ip": "127.0.0.1"})

    agg = ComponentStatDaily.objects.filter(page_id="home", slot_id="hero", date=target_date).first()
    ok = bool(agg) and agg.impressions == 1 and agg.clicks == 1 and round(agg.avg_scroll_pct) == 80

    return {
        "ok": ok,
        "name": __name__,
        "duration": round(time.time() - started, 3),
        "logs": [
            f"impressions={getattr(agg, 'impressions', None)}",
            f"clicks={getattr(agg, 'clicks', None)}",
            f"avg_scroll={getattr(agg, 'avg_scroll_pct', None)}",
        ],
    }
