from __future__ import annotations

from uuid import uuid4
from unittest.mock import patch

from django.conf import settings
from django.test import Client, TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from apps.atelier.analytics import tasks
from apps.atelier.analytics.models import (
    AnalyticsEventRaw,
    ComponentStatDaily,
    HeatmapBucketDaily,
)
from apps.atelier.analytics.serializers import EventItemSerializer
from apps.atelier.analytics.throttling import AnalyticsIPThrottle


class AnalyticsSerializerTests(TestCase):
    def test_event_serializer_rejects_invalid_type(self):
        serializer = EventItemSerializer(data={
            "event_uuid": str(uuid4()),
            "event_type": "invalid",
            "page_id": "home",
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn("event_type", serializer.errors)

    def test_event_serializer_validates_heatmap_coordinates(self):
        serializer = EventItemSerializer(data={
            "event_uuid": str(uuid4()),
            "event_type": "heatmap",
            "page_id": "home",
            "payload": {"x": 0.5},
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn("payload", serializer.errors)

    def test_event_serializer_enforces_payload_limit(self):
        payload = {f"k{i}": i for i in range(40)}
        serializer = EventItemSerializer(data={
            "event_uuid": str(uuid4()),
            "event_type": "view",
            "page_id": "home",
            "payload": payload,
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn("payload", serializer.errors)


class AnalyticsCollectAPITests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_collect_requires_consent(self):
        with patch.object(tasks.persist_raw, "delay") as mock_delay:
            response = self.client.post(
                "/api/analytics/collect/",
                data={"events": []},
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 204)
        mock_delay.assert_not_called()

    def test_collect_persists_events_and_rollup(self):
        AnalyticsEventRaw.objects.all().delete()
        ComponentStatDaily.objects.all().delete()
        payload = {
            "events": [
                {
                    "event_uuid": str(uuid4()),
                    "event_type": "view",
                    "page_id": "home",
                    "slot_id": "hero",
                    "component_alias": "core/hero",
                }
            ]
        }

        with patch.object(tasks.persist_raw, "delay", side_effect=lambda events, meta=None: tasks.persist_raw.run(events, meta)), \
             patch.object(tasks.rollup_incremental, "delay", side_effect=lambda *args, **kwargs: tasks.rollup_incremental.run(*args, **kwargs)):
            self.client.cookies[settings.CONSENT_COOKIE_NAME] = "yes"
            response = self.client.post(
                "/api/analytics/collect/",
                data=payload,
                content_type="application/json",
                HTTP_USER_AGENT="pytest",
            )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(AnalyticsEventRaw.objects.count(), 1)
        self.assertTrue(ComponentStatDaily.objects.filter(page_id="home", slot_id="hero").exists())

    def test_throttle_generates_cache_key(self):
        throttle = AnalyticsIPThrottle()
        factory = APIRequestFactory()
        request = factory.post("/api/analytics/collect/")
        request.META["REMOTE_ADDR"] = "203.0.113.1"
        key = throttle.get_cache_key(request, None)
        self.assertIsNotNone(key)
        self.assertIn("analytics_collect", key)


class AnalyticsTaskTests(TestCase):
    def setUp(self):
        AnalyticsEventRaw.objects.all().delete()
        ComponentStatDaily.objects.all().delete()
        HeatmapBucketDaily.objects.all().delete()

    def test_persist_raw_is_idempotent(self):
        event_id = str(uuid4())
        event = {
            "event_uuid": event_id,
            "event_type": "view",
            "page_id": "home",
            "slot_id": "hero",
            "component_alias": "core/hero",
            "ts": timezone.now().isoformat(),
        }
        with patch.object(tasks.rollup_incremental, "delay", side_effect=lambda *args, **kwargs: None):
            tasks.persist_raw.run([event], meta={})
            tasks.persist_raw.run([event], meta={})
        self.assertEqual(AnalyticsEventRaw.objects.filter(event_uuid=event_id).count(), 1)

    def test_heatmap_bucket_clamped(self):
        now = timezone.now()
        events = [
            {
                "event_uuid": str(uuid4()),
                "event_type": "heatmap",
                "page_id": "home",
                "slot_id": "hero",
                "component_alias": "core/hero",
                "ts": now.isoformat(),
                "payload": {"x": 1.7, "y": -0.4},
            }
        ]
        with patch.object(tasks.rollup_incremental, "delay", side_effect=lambda *args, **kwargs: tasks.rollup_incremental.run(*args, **kwargs)):
            tasks.persist_raw.run(events, meta={})
        bucket = HeatmapBucketDaily.objects.filter(page_id="home", date=now.date()).first()
        self.assertIsNotNone(bucket)
        self.assertEqual(bucket.bucket_x, 99)
        self.assertEqual(bucket.bucket_y, 0)
