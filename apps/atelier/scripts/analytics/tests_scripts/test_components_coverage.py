from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.utils import timezone

from apps.atelier.analytics import tasks
from apps.atelier.analytics.models import AnalyticsEventRaw, ComponentStatDaily


def _component_aliases() -> list[str]:
    root = Path(settings.BASE_DIR) / "templates" / "components"
    if not root.exists():
        return []
    aliases: list[str] = []
    for tpl in root.rglob("*.html"):
        rel = tpl.relative_to(root)
        parts = rel.with_suffix("").parts
        if not parts:
            continue
        alias = "/".join(parts)
        if len(alias) > 120:
            alias = alias[-120:]
        aliases.append(alias)
    return sorted(set(aliases))


def _build_event(alias: str, ts_iso: str) -> dict:
    slot_id = alias.replace("/", "_")[:120]
    return {
        "event_uuid": str(uuid4()),
        "event_type": "view",
        "page_id": "components_coverage",
        "slot_id": slot_id,
        "component_alias": alias,
        "ts": ts_iso,
    }


def run():
    started = time.time()
    AnalyticsEventRaw.objects.filter(page_id="components_coverage").delete()
    ComponentStatDaily.objects.filter(page_id="components_coverage").delete()

    aliases = _component_aliases()
    now = timezone.now().isoformat()
    batch: list[dict] = []

    with patch.object(tasks.persist_raw, "delay", side_effect=lambda events, meta=None: tasks.persist_raw.run(events, meta)), \
         patch.object(tasks.rollup_incremental, "delay", side_effect=lambda *args, **kwargs: tasks.rollup_incremental.run(*args, **kwargs)):
        for alias in aliases:
            batch.append(_build_event(alias, now))
            if len(batch) >= 40:
                tasks.persist_raw.run(batch, meta={"user_agent": "coverage", "ip": "127.0.0.1"})
                batch = []
        if batch:
            tasks.persist_raw.run(batch, meta={"user_agent": "coverage", "ip": "127.0.0.1"})

    expected = len(aliases)
    actual = ComponentStatDaily.objects.filter(page_id="components_coverage").count()
    ok = actual == expected

    return {
        "ok": ok,
        "name": __name__,
        "duration": round(time.time() - started, 3),
        "logs": [
            f"aliases={expected}",
            f"records={actual}",
        ],
    }
