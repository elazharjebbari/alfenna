from __future__ import annotations

import json
import time
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.test import Client

from apps.atelier.analytics import tasks
from apps.atelier.analytics.models import AnalyticsEventRaw, ComponentStatDaily


def run():
    started = time.time()
    AnalyticsEventRaw.objects.all().delete()
    ComponentStatDaily.objects.all().delete()

    client = Client()
    payload = {
        "events": [
            {
                "event_uuid": str(uuid4()),
                "event_type": "view",
                "page_id": "home",
                "slot_id": "hero",
                "component_alias": "core/hero",
                "payload": {"source": "test"},
            }
        ]
    }

    with patch.object(tasks.persist_raw, "delay", side_effect=lambda events, meta=None: tasks.persist_raw.run(events, meta)), \
         patch.object(tasks.rollup_incremental, "delay", side_effect=lambda *args, **kwargs: tasks.rollup_incremental.run(*args, **kwargs)):
        client.cookies[settings.CONSENT_COOKIE_NAME] = "yes"
        response = client.post(
            "/api/analytics/collect/",
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_USER_AGENT="AnalyticsScript/1.0",
        )

    inserted = AnalyticsEventRaw.objects.filter(page_id="home", slot_id="hero").count()
    aggregate_exists = ComponentStatDaily.objects.filter(page_id="home", slot_id="hero").exists()
    ok = response.status_code in (202, 200) and inserted == 1 and aggregate_exists

    return {
        "ok": ok,
        "name": __name__,
        "duration": round(time.time() - started, 3),
        "logs": [
            f"status={response.status_code}",
            f"inserted={inserted}",
            f"aggregate={aggregate_exists}",
        ],
    }
