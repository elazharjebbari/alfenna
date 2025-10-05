from django.test import SimpleTestCase, override_settings
from django.urls import resolve


class MessagingSmokeTests(SimpleTestCase):
    @override_settings(ROOT_URLCONF="lumierelearning.urls")
    def test_healthcheck_endpoint_exists(self) -> None:
        resolver = resolve("/email/health/")
        self.assertTrue(callable(resolver.func))

    @override_settings(ROOT_URLCONF="lumierelearning.urls")
    def test_healthcheck_response(self) -> None:
        response = self.client.get("/email/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["app"], "messaging")
