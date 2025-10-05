from django.test import RequestFactory, TestCase

from apps.atelier.compose.hydrators.forms.hydrators import forms_shell, wizard_generic


class WizardContractTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    def test_shell_passes_flow_key_to_child(self) -> None:
        request = self.factory.get("/")
        shell_ctx = forms_shell(request, params={})
        child = shell_ctx["children"]["wizard"]
        self.assertIn("flow_key", child)
        self.assertTrue(child["flow_key"])

    def test_wizard_requires_flow_key(self) -> None:
        request = self.factory.get("/")
        with self.assertRaises(KeyError):
            wizard_generic(request, params={})

    def test_wizard_returns_sha1_for_cache(self) -> None:
        request = self.factory.get("/")
        shell_ctx = forms_shell(request, params={})
        child = shell_ctx["children"]["wizard"]
        ctx = wizard_generic(request, params={
            "flow_key": child["flow_key"],
            "backend_config": child["backend_config"],
            "ui_texts": child["ui_texts"],
            "schema": child["schema"],
        })
        self.assertTrue(ctx["config_json"])
        self.assertTrue(ctx["config_sha1"])
        self.assertEqual(len(ctx["config_sha1"]), 40)
