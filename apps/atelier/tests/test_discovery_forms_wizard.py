from django.test import TestCase

from apps.atelier.components import registry


class DiscoveryFormsWizardTests(TestCase):
    def test_core_registered(self) -> None:
        self.assertTrue(registry.exists("forms/wizard_generic", namespace="core"))

    def test_ma_fallback_to_core(self) -> None:
        component_meta = registry.get("forms/wizard_generic", namespace="ma")
        self.assertEqual(component_meta["template"], "components/core/forms/wizard.html")
