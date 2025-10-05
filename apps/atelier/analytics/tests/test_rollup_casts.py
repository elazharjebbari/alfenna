from __future__ import annotations

from django.db.models.fields.json import KeyTextTransform
from django.db.models import Avg, FloatField, Q
from django.db.models.functions import Cast
from django.test import TestCase
from django.utils import timezone

from apps.atelier.analytics.models import AnalyticsEventRaw


class RollupJsonCastTests(TestCase):
    def setUp(self) -> None:
        now = timezone.now()
        base = {
            "ts": now,
            "page_id": "login",
            "site_version": "core",
            "slot_id": "hero",
            "component_alias": "hero/main",
        }
        import uuid

        for value in ("10", "20", "30"):
            AnalyticsEventRaw.objects.create(
                event_type="scroll",
                payload={"scroll_pct": value},
                event_uuid=str(uuid.uuid4()),
                **base,
            )

    def test_avg_scroll_pct_casts_to_float(self) -> None:
        qs = AnalyticsEventRaw.objects.filter(page_id="login", site_version="core")
        result = qs.aggregate(
            avg=Avg(
                Cast(KeyTextTransform("scroll_pct", "payload"), FloatField()),
                filter=Q(event_type="scroll"),
            )
        )
        self.assertAlmostEqual(result["avg"], 20.0, places=6)
