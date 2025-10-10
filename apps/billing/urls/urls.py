from django.urls import path

from ..views.checkout import cancel_view, create_checkout_session, health_view, success_view, sandbox_view
from ..views.invoice import invoice_download_view
from ..webhooks import stripe_webhook_view

app_name = "billing"
urlpatterns = [
    path("checkout/", create_checkout_session, name="create_checkout_session"),
    path("intent/create/", create_checkout_session, name="create_payment_intent"),
    path("success/", success_view, name="success"),
    path("cancel/", cancel_view, name="cancel"),
    path("sandbox/", sandbox_view, name="sandbox"),
    path("webhooks/stripe/", stripe_webhook_view, name="webhook"),
    path("health/", health_view, name="health"),
    path("invoices/<int:order_id>/", invoice_download_view, name="invoice-download"),
]
