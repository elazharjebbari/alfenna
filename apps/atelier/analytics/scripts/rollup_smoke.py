from __future__ import annotations

from django.utils import timezone

from apps.atelier.analytics.models import AnalyticsEventRaw
from apps.atelier.analytics.tasks import rollup_incremental


def run(*args):
    day = args[0] if args else timezone.now().date().isoformat()
    page_id = args[1] if len(args) > 1 else "login"
    site_version = args[2] if len(args) > 2 else "core"

    print("\n=== ROLLUP SMOKE ===")
    now = timezone.now()
    for value in ("10", "20", "30"):
        AnalyticsEventRaw.objects.create(
            ts=now,
            page_id=page_id,
            site_version=site_version,
            slot_id="hero",
            component_alias="hero/main",
            event_type="scroll",
            payload={"scroll_pct": value},
        )
    print("Inserted scroll events.")
    rollup_incremental.delay(day, page_id, site_version)
    print(f"Triggered rollup_incremental for {day} {page_id} {site_version}.\n")
