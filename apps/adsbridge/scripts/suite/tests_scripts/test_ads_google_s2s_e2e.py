"""End-to-end harness for the Google Ads S2S bridge."""

from __future__ import annotations

import json
import os
import uuid
from decimal import Decimal

from django.conf import settings
from django.core import signing
from django.core.management import CommandError, call_command
from django.test import Client

from apps.adsbridge import conf as ads_conf, services, tasks
from apps.adsbridge.adapters.google_ads import GoogleAdsAdapter, GoogleAdsAdapterError
from apps.adsbridge.models import ConversionRecord
from apps.billing.models import Order, OrderStatus
from apps.billing.services import EntitlementService
from apps.billing.webhooks import _process_event
from apps.leads.models import Lead


def _log(message: str, **extra) -> None:
    payload = " ".join(f"{key}={value}" for key, value in extra.items())
    print(f"[ADS-E2E] {message}{(' ' + payload) if payload else ''}")


def run() -> None:
    """Execute a dry-run scenario: attribution → lead → purchase → refund."""

    if os.getenv("E2E_ONLINE", "").strip().lower() in {"1", "true", "yes"}:
        from .test_ads_google_s2s_live import run as run_live

        run_live()
        return

    # Ensure eager execution and feature toggle enabled for the harness run.
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
    settings.GADS_ENABLED = True
    settings.GADS_VALIDATE_ONLY = True
    settings.GADS_PARTIAL_FAILURE = True
    settings.ADS_S2S_MODE = "mock"

    try:
        call_command("ads_verify_actions", alias="lead_submit", strict=True)
    except (CommandError, SystemExit) as exc:
        raise RuntimeError(
            "Preflight failed: missing or invalid lead_submit conversion action"
        ) from exc

    services.load_ads_config.cache_clear()
    tasks._get_adapter.cache_clear()

    try:
        GoogleAdsAdapter.load_configuration()
    except GoogleAdsAdapterError as exc:
        raise RuntimeError(f"Google Ads configuration invalid: {exc}") from exc

    client = Client()
    client.cookies[settings.CONSENT_COOKIE_NAME] = "true"

    gclid = "E2E-MOCK-GCLID"
    signed_cookie = signing.dumps({"gclid": gclid}, salt="adsbridge.attribution")
    client.cookies[settings.ADSBRIDGE_ATTRIBUTION_COOKIE if hasattr(settings, "ADSBRIDGE_ATTRIBUTION_COOKIE") else "ll_ads_attr"] = signed_cookie
    _log("Attribution cookie primed", gclid=gclid)

    # Prepare lead payload using contact_full policy (email required).
    unique_email = f"ads-e2e+{uuid.uuid4().hex[:8]}@example.com"
    lead_payload = {
        "form_kind": "contact_full",
        "email": unique_email,
        "first_name": "Ads",
        "last_name": "Bridge",
        "consent": True,
        "context": {"scenario": "ads-e2e"},
    }

    sign_response = client.post(
        "/api/leads/sign/",
        data=json.dumps({"payload": lead_payload}),
        content_type="application/json",
    )
    if sign_response.status_code != 200:
        raise RuntimeError("Unable to obtain signed token")
    signed_token = sign_response.json()["signed_token"]
    lead_payload["signed_token"] = signed_token

    idem_key = f"ads-e2e-{uuid.uuid4().hex}"
    create_response = client.post(
        "/api/leads/collect/",
        data=json.dumps(lead_payload),
        content_type="application/json",
        HTTP_X_IDEMPOTENCY_KEY=idem_key,
    )
    if create_response.status_code != 202:
        raise RuntimeError(f"Lead submission failed: {create_response.status_code} {create_response.content}")
    lead_id = create_response.json()["lead_id"]
    _log("Lead collected", lead_id=lead_id)

    lead = Lead.objects.get(id=lead_id)
    lead.refresh_from_db()

    lead_record = ConversionRecord.objects.get(kind=ConversionRecord.Kind.LEAD, lead_id=str(lead_id))
    lead_record.refresh_from_db()
    mode = ads_conf.current_mode()
    _log("ADS mode resolved", mode=mode)
    capture_mode = mode == "capture"
    if mode == "off":
        raise RuntimeError("ADS_S2S_MODE=off — conversions are disabled")
    if capture_mode:
        if lead_record.status != ConversionRecord.Status.HELD:
            raise RuntimeError(
                f"Capture mode expected HELD status for lead, got {lead_record.status}"
            )
        _log("Lead held (capture mode)", record_id=lead_record.id, status=lead_record.status)
    else:
        if lead_record.status != ConversionRecord.Status.SENT:
            raise RuntimeError(f"Lead conversion not sent (status={lead_record.status})")
        _log("Lead uploaded", record_id=lead_record.id, status=lead_record.status)

    # Simulate a paid order linked to the lead.
    order = Order.objects.create(
        email=lead.email,
        amount_subtotal=25000,
        tax_amount=0,
        amount_total=25000,
        currency="EUR",
        status=OrderStatus.PENDING,
        idempotency_key=f"order-{uuid.uuid4().hex}",
    )
    lead.order = order
    lead.save(update_fields=["order"])

    entitlement_payload = {
        "data": {"object": {"metadata": {"order_id": str(order.id)}, "amount_received": order.amount_total, "currency": order.currency.lower()}},
    }
    EntitlementService.grant_entitlement(order, "payment_intent.succeeded", entitlement_payload)

    purchase_record = ConversionRecord.objects.filter(kind=ConversionRecord.Kind.PURCHASE, order_id=str(order.id)).latest("id")
    purchase_record.refresh_from_db()
    if capture_mode:
        if purchase_record.status != ConversionRecord.Status.HELD:
            raise RuntimeError(
                f"Capture mode expected HELD status for purchase, got {purchase_record.status}"
            )
        _log("Purchase held (capture mode)", record_id=purchase_record.id)
    else:
        if purchase_record.status != ConversionRecord.Status.SENT:
            raise RuntimeError(f"Purchase conversion not sent (status={purchase_record.status})")
        _log("Purchase uploaded", record_id=purchase_record.id, value=str(purchase_record.value))

    refund_event = {
        "type": "charge.refunded",
        "data": {"object": {"metadata": {"order_id": str(order.id)}}},
    }
    _process_event(refund_event)

    adjustment_record = ConversionRecord.objects.filter(kind=ConversionRecord.Kind.ADJUSTMENT, order_id=str(order.id)).latest("id")
    adjustment_record.refresh_from_db()
    if capture_mode:
        if adjustment_record.status != ConversionRecord.Status.HELD:
            raise RuntimeError(
                f"Capture mode expected HELD status for adjustment, got {adjustment_record.status}"
            )
        _log(
            "Adjustment held (capture mode)",
            record_id=adjustment_record.id,
            type=adjustment_record.adjustment_type,
        )
    else:
        if adjustment_record.status != ConversionRecord.Status.SENT:
            raise RuntimeError(
                f"Adjustment conversion not sent (status={adjustment_record.status})"
            )
        _log("Adjustment uploaded", record_id=adjustment_record.id, type=adjustment_record.adjustment_type)

    _log(
        "Scenario complete",
        lead_record=lead_record.id,
        purchase_record=purchase_record.id,
        adjustment_record=adjustment_record.id,
    )
