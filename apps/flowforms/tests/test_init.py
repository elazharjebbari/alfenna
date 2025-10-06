from django.test import TestCase
from django.apps import apps as dj_apps
from django.urls import reverse

from apps.flowforms.tasks import debug_ping

# apps/flowforms/tests/test_init.py (modifie seulement la clé utilisée)
from django.test import TestCase
from django.apps import apps as dj_apps
from django.urls import reverse
from apps.flowforms.tasks import debug_ping

class FlowFormsInitTests(TestCase):
    def test_app_loads(self):
        self.assertTrue(dj_apps.is_installed("apps.flowforms"), "apps.flowforms non installé")

        # Utilise une clé existante dans ta config YAML
        url = reverse("flowforms:wizard", kwargs={"flow_key": "checkout_intent_flow"})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200, resp.content[:200])
        self.assertIn(b"FlowForms", resp.content)  # contenu rendu par wizard.html

    def test_celery_is_configured(self):
        """
        Vérifie qu’une tâche Celery peut s’exécuter en synchrone via .apply().
        (ne nécessite PAS de worker)
        """
        result = debug_ping.apply(kwargs={"echo": "hello"})
        self.assertFalse(result.failed(), f"Echec tâche Celery: {result.info}")
        payload = result.get()
        self.assertIsInstance(payload, dict)
        self.assertEqual(payload.get("echo"), "hello")
        self.assertIn("now", payload)