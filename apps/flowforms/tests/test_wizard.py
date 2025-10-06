from __future__ import annotations
import tempfile
from pathlib import Path

from django.test import TestCase, override_settings
from django.urls import reverse
import yaml

from apps.flowforms.conf.loader import invalidate_config_cache
from apps.flowforms.models import FlowSession, FlowStatus


class FlowFormsWizardTests(TestCase):
    def setUp(self):
        # YAML minimal dédié au wizard (3 steps linéaires)
        self.flow = {
            "flows": [
                {
                    "key": "wizard_flow",
                    "kind": "checkout_intent",
                    "steps": [
                        {
                            "key": "s1",
                            "title": "Vos coordonnées",
                            "fields": [
                                {"name": "email", "type": "email", "required": True, "label": "Email"},
                            ],
                            "ctas": [{"action": "next", "label": "Continuer"}],
                        },
                        {
                            "key": "s2",
                            "title": "Téléphone",
                            "fields": [
                                {"name": "phone", "type": "phone", "required": False, "label": "Phone"},
                            ],
                            "ctas": [
                                {"action": "prev", "label": "Retour"},
                                {"action": "next", "label": "Suivant"},
                            ],
                        },
                        {
                            "key": "s3",
                            "title": "Validation",
                            "fields": [],
                            "ctas": [{"action": "submit", "label": "Envoyer"}],
                        },
                    ],
                }
            ]
        }
        self.tmpdir = tempfile.TemporaryDirectory()
        self.yaml_path = Path(self.tmpdir.name) / "wizard.yaml"
        self.yaml_path.write_text(yaml.safe_dump(self.flow, sort_keys=False), encoding="utf-8")

        self.override = override_settings(FLOWFORMS_POLICY_YAML=str(self.yaml_path))
        self.override.enable()
        invalidate_config_cache()

        self.url = reverse("flowforms:wizard", kwargs={"flow_key": "wizard_flow"})

    def tearDown(self):
        self.override.disable()
        self.tmpdir.cleanup()

    def test_wizard_linear_submit_calls_done(self):
        # GET s1
        r = self.client.get(self.url)
        self.assertContains(r, "FlowForms")
        self.assertContains(r, "Vos coordonnées")

        # POST s1 -> s2
        r = self.client.post(self.url, data={
            "email": "u@ex.com",
            "flowforms_action": "next::",
        }, follow=True)
        self.assertContains(r, "Téléphone")

        # POST s2 -> s3
        r = self.client.post(self.url, data={
            "phone": "+212600000000",
            "flowforms_action": "next::",
        }, follow=True)
        self.assertContains(r, "Validation")

        # POST s3 (submit) -> done + FlowSession COMPLETED
        r = self.client.post(self.url, data={
            "flowforms_action": "submit::",
        }, follow=True)
        self.assertContains(r, "Merci !")
        # statut
        fs = FlowSession.objects.first()
        self.assertEqual(fs.status, FlowStatus.COMPLETED)

    def test_wizard_renders_theme_classes(self):
        r = self.client.get(self.url)
        # vérifie que les classes du CTA par défaut existent (depuis _cta_bar)
        self.assertContains(r, 'class="btn')

    def test_goto_done_without_side_effects_when_invalid(self):
        # submit sans email (step s1 invalide) => on reste sur place
        r = self.client.post(self.url, data={"flowforms_action": "submit::"}, follow=True)
        # toujours s1 (pas "Merci !")
        self.assertContains(r, "Vos coordonnées")
        self.assertNotContains(r, "Merci !")
        fs = FlowSession.objects.first()
        # pas complété
        self.assertIsNotNone(fs)
        self.assertEqual(fs.status, FlowStatus.ACTIVE)