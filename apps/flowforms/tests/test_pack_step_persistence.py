from django.test import TestCase
from django.urls import reverse

from apps.flowforms.models import FlowSession
from apps.leads.models import Lead


class PackStepPersistenceTests(TestCase):
    def setUp(self):
        self.url = reverse("flowforms:wizard", kwargs={"flow_key": "checkout_intent_flow"})

    def _post_step1(self, email="user@example.com", phone=""):
        return self.client.post(
            self.url,
            data={"email": email, "phone": phone, "flowforms_action": "next::"},
            follow=True,
        )

    def test_step2_requires_pack_and_persists_immediately(self):
        response = self._post_step1()
        self.assertIn(response.status_code, (200, 302))
        html = response.content.decode("utf-8")
        self.assertIn("Pack Solo", html)

        fs = FlowSession.objects.get(flow_key="checkout_intent_flow")
        lead = Lead.objects.get(pk=fs.lead_id)

        missing_pack = self.client.post(self.url, data={"flowforms_action": "next::"})
        self.assertEqual(missing_pack.status_code, 200)
        err_html = missing_pack.content.decode("utf-8")
        self.assertTrue(
            "Ce champ est obligatoire" in err_html or "This field is required" in err_html
        )
        lead.refresh_from_db()
        self.assertEqual(lead.pack_slug, "")

        ok_step2 = self.client.post(
            self.url,
            data={
                "pack_slug": "solo",
                "full_name": "Alice",
                "flowforms_action": "next::",
            },
        )
        self.assertIn(ok_step2.status_code, (302, 200))
        lead.refresh_from_db()
        self.assertEqual(lead.pack_slug, "solo")
        self.assertEqual(lead.full_name, "Alice")
        self.assertEqual(
            FlowSession.objects.get(pk=fs.pk).data_snapshot.get("pack_slug"),
            "solo",
        )

    def test_submit_final_keeps_pack_slug(self):
        self._post_step1()
        self.client.post(
            self.url,
            data={"pack_slug": "solo", "flowforms_action": "next::"},
        )
        step3 = self.client.post(
            self.url,
            data={
                "currency": "MAD",
                "accept_terms": "on",
                "flowforms_action": "submit::",
            },
            follow=True,
        )
        self.assertIn(step3.status_code, (200, 302))

        fs = FlowSession.objects.get(flow_key="checkout_intent_flow")
        fs.refresh_from_db()
        self.assertEqual(fs.data_snapshot.get("pack_slug"), "solo")

        lead = Lead.objects.get(pk=fs.lead_id)
        lead.refresh_from_db()
        self.assertEqual(lead.pack_slug, "solo")

    def test_lookup_does_not_use_pack_slug(self):
        existing = Lead.objects.create(
            form_kind="checkout_intent",
            email="other@example.com",
            idempotency_key="test-existing",
            pack_slug="solo",
        )

        self._post_step1(email="fresh@example.com")
        fs = FlowSession.objects.get(flow_key="checkout_intent_flow")
        self.assertNotEqual(fs.lead_id, existing.id)

        self.client.post(
            self.url,
            data={"pack_slug": "solo", "flowforms_action": "next::"},
        )
        fs.refresh_from_db()
        self.assertNotEqual(fs.lead_id, existing.id)
        self.assertEqual(
            Lead.objects.filter(form_kind="checkout_intent").count(),
            2,
        )
