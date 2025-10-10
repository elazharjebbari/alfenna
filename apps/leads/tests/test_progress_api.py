# apps/leads/tests/test_progress_api.py
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from apps.leads.models import Lead
from apps.leads.constants import FormKind

class ProgressAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_step2_persists_pack_slug(self):
        url = reverse("leads:progress")
        headers = {"HTTP_X_IDEMPOTENCY_KEY": "flow:checkout_intent_flow:demo-session:step:2"}
        payload = {
            "form_kind": FormKind.CHECKOUT_INTENT,
            "flow_key": "checkout_intent_flow",
            "ff_session_key": "demo-session",
            "email": "user@example.com",
            "offer_key": "duo",
            "pack_slug": "duo",
            "quantity": 1,
            "context.complementary_slugs": ["serum-vitc"]
        }
        res = self.client.post(url, payload, format="json", **headers)
        self.assertEqual(res.status_code, 200)
        lead = Lead.objects.get(email="user@example.com")
        self.assertEqual(getattr(lead, "pack_slug", ""), "duo")
        self.assertIn("complementary_slugs", lead.context)
        self.assertEqual(lead.context["complementary_slugs"], ["serum-vitc"])
