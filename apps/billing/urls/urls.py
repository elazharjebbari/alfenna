from django.urls import path

from ..views.checkout import cancel_view, create_checkout_session, health_view, success_view, sandbox_view
from ..views.checkout_pack import (
    checkout_pack_view,
    create_payment_intent_view,
    preview_totals_view,
)
from ..views.invoice import invoice_download_view
from ..webhooks import stripe_webhook_view

app_name = "billing"
urlpatterns = [
    path("checkout/", create_checkout_session, name="create_checkout_session"),
    path("checkout/pack/<slug:slug>/", checkout_pack_view, name="checkout_pack"),
    path("preview/", preview_totals_view, name="preview_totals"),
    path("intent/create/", create_payment_intent_view, name="create_payment_intent"),
    path("success/", success_view, name="success"),
    path("cancel/", cancel_view, name="cancel"),
    path("sandbox/", sandbox_view, name="sandbox"),
    path("webhook/", stripe_webhook_view, name="webhook"),
    path("webhooks/stripe/", stripe_webhook_view, name="webhook_legacy"),
    path("health/", health_view, name="health"),
    path("invoices/<int:order_id>/", invoice_download_view, name="invoice-download"),
]
