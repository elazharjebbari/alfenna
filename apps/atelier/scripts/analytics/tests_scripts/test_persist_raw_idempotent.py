from __future__ import annotations

import time
from unittest.mock import patch
from uuid import uuid4

from django.utils import timezone

from apps.atelier.analytics import tasks
from apps.atelier.analytics.models import AnalyticsEventRaw


def run():
    started = time.time()
    AnalyticsEventRaw.objects.all().delete()

    event_id = str(uuid4())
    events = [
        {
            "event_uuid": event_id,
            "event_type": "view",
            "page_id": "home",
            "slot_id": "hero",
            "component_alias": "core/hero",
            "ts": timezone.now().isoformat(),
        }
    ]

    with patch.object(tasks.rollup_incremental, "delay", side_effect=lambda *args, **kwargs: None):
        tasks.persist_raw.run(events, meta={})
        tasks.persist_raw.run(events, meta={})

    count = AnalyticsEventRaw.objects.filter(event_uuid=event_id).count()
    ok = count == 1

    return {
        "ok": ok,
        "name": __name__,
        "duration": round(time.time() - started, 3),
        "logs": [f"stored={count}"],
    }
