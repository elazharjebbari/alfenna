from __future__ import annotations
import tempfile, yaml
from pathlib import Path
from django.test import TestCase, override_settings
from django.urls import reverse
from apps.leads.models import LeadSubmissionLog
from apps.leads.constants import LeadStatus

class FlowFormsSubmissionIntegrationTests(TestCase):
    def setUp(self):
        flow = {
            "flows": [
                {
                    "key": "wizard_submit_flow",
                    "kind": "checkout_intent",
                    "steps": [
                        {"key": "s1", "title": "Email", "fields": [{"name": "email", "type": "email", "required": True}],
                         "ctas": [{"action": "next", "label": "Next"}]},
                        {"key": "s2", "title": "Phone", "fields": [{"name": "phone", "type": "phone"}],
                         "ctas": [{"action": "submit", "label": "Envoyer"}]},
                    ],
                }
            ]
        }
        self.tmpdir = tempfile.TemporaryDirectory()
        p = Path(self.tmpdir.name) / "f.yaml"
        p.write_text(yaml.safe_dump(flow, sort_keys=False), encoding="utf-8")
        self.override = override_settings(FLOWFORMS_POLICY_YAML=str(p))
        self.override.enable()
        from apps.flowforms.conf.loader import invalidate_config_cache
        invalidate_config_cache()
        self.url = reverse("flowforms:wizard", kwargs={"flow_key": "wizard_submit_flow"})

    def tearDown(self):
        self.override.disable()
        self.tmpdir.cleanup()

    def test_wizard_submit_logs_success(self):
        r = self.client.get(self.url)
        self.assertContains(r, "Email")
        r = self.client.post(self.url, data={"email": "u@ex.com", "flowforms_action": "next::"}, follow=True)
        self.assertContains(r, "Phone")
        r = self.client.post(self.url, data={"phone": "+212600000000", "flowforms_action": "submit::"}, follow=True)
        self.assertContains(r, "Merci !")
        log = LeadSubmissionLog.objects.first()
        self.assertIsNotNone(log)
        self.assertEqual(log.status, LeadStatus.VALID)