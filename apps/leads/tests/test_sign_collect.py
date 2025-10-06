from __future__ import annotations

import json
from uuid import uuid4

from django.test import Client, TestCase, override_settings


class LeadSignCollectFlowTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()

    def test_sign_and_collect_roundtrip(self) -> None:
        final_body = {
            "form_kind": "product_lead",
            "full_name": "Test User",
            "phone": "+212600000001",
            "address": "Casablanca",
            "offer_key": "duo",
            "payment_method": "cod",
            "consent": True,
            "context": {"utm_source": "test"},
        }

        sign_response = self.client.post(
            "/api/leads/sign/",
            data=json.dumps({"payload": final_body}),
            content_type="application/json",
        )
        self.assertEqual(sign_response.status_code, 200)
        token = sign_response.json().get("signed_token")
        self.assertTrue(token)

        collect_body = dict(final_body, signed_token=token)
        collect_headers = {"HTTP_X_IDEMPOTENCY_KEY": f"test-{uuid4().hex}"}

        collect_response = self.client.post(
            "/api/leads/collect/",
            data=json.dumps(collect_body),
            content_type="application/json",
            **collect_headers,
        )

        self.assertIn(collect_response.status_code, {200, 202})

    @override_settings(LEADS_SIGNATURE_IGNORE_FIELDS=["upsell_note"])
    def test_tolerant_signature_ignores_configured_fields(self) -> None:
        unsigned_body = {
            "form_kind": "product_lead",
            "full_name": "Test User",
            "phone": "+212600000003",
            "payment_method": "cod",
            "consent": True,
        }

        sign_response = self.client.post(
            "/api/leads/sign/",
            data=json.dumps({"payload": unsigned_body}),
            content_type="application/json",
        )
        self.assertEqual(sign_response.status_code, 200)
        token = sign_response.json().get("signed_token")

        collect_body = dict(unsigned_body, signed_token=token, upsell_note="late-stage", context={"utm_source": "ignored"})
        collect_headers = {"HTTP_X_IDEMPOTENCY_KEY": f"test-{uuid4().hex}"}

        collect_response = self.client.post(
            "/api/leads/collect/",
            data=json.dumps(collect_body),
            content_type="application/json",
            **collect_headers,
        )

        self.assertIn(collect_response.status_code, {200, 202})
