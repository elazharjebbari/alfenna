from django.test import Client, TestCase
from django.urls import reverse


class SandboxViewTests(TestCase):
    def test_sandbox_view_returns_200(self) -> None:
        client = Client()
        url = reverse("billing:sandbox") + "?sid=test-session&paid=1"
        response = client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"test-session", response.content)
        self.assertIn(b"Paid", response.content)
