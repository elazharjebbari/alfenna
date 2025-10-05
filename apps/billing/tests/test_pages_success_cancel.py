from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(BILLING_ENABLED=True, STRIPE_SECRET_KEY="", STRIPE_PUBLISHABLE_KEY="pk_test_pages")
class BillingPagesTests(TestCase):
    def test_success_page_renders(self) -> None:
        response = self.client.get(reverse("billing:success"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "billing-outcome--success")

    def test_cancel_page_renders(self) -> None:
        response = self.client.get(reverse("billing:cancel"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "billing-outcome--cancel")
