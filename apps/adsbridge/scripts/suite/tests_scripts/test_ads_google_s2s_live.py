"""Live validation harness for Google Ads S2S uploads."""

from __future__ import annotations

import json
import os
import uuid

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
    print(f"[ADS-E2E-LIVE] {message}{(' ' + payload) if payload else ''}")


def _raise_with_payload(record: ConversionRecord, stage: str) -> None:
    payload = record.google_upload_status or {}
    code = payload.get("error_code") or record.last_error or "UNKNOWN"
    detail = payload.get("error_detail") or record.last_error or ""
    errors = payload.get("errors") or []
    status_message = payload.get("status_message")
    _log(
        f"{stage} conversion error",
        record_id=record.id,
        code=code,
        detail=detail,
        status_message=status_message,
        errors=errors,
    )
    raise RuntimeError(f"{stage} conversion failed: code={code} detail={detail}")


def run() -> None:
    """Run the live validation flow (validate_only + partial_failure)."""

    if os.getenv("E2E_ONLINE", "").strip().lower() not in {"1", "true", "yes"}:
        raise RuntimeError("E2E_ONLINE=1 requis pour lancer la validation live.")

    gclid = os.getenv("GADS_TEST_GCLID", "").strip()
    if not gclid:
        raise RuntimeError("GADS_TEST_GCLID manquant: fournir un GCLID de test valide.")

    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
    settings.GADS_ENABLED = True
    settings.GADS_VALIDATE_ONLY = True
    settings.GADS_PARTIAL_FAILURE = True
    settings.ADS_S2S_MODE = "on"

    try:
        call_command("ads_verify_actions", alias="lead_submit", strict=True)
    except (CommandError, SystemExit) as exc:
        raise RuntimeError(
            "Preflight failed: conversion action lead_submit introuvable"
        ) from exc

    services.load_ads_config.cache_clear()
    tasks._get_adapter.cache_clear()

    try:
        GoogleAdsAdapter.load_configuration()
    except GoogleAdsAdapterError as exc:
        raise RuntimeError(f"Google Ads configuration invalid: {exc}") from exc

    client = Client()
    client.cookies[settings.CONSENT_COOKIE_NAME] = "true"
    signed_cookie = signing.dumps({"gclid": gclid}, salt="adsbridge.attribution")
    cookie_name = (
        settings.ADSBRIDGE_ATTRIBUTION_COOKIE
        if hasattr(settings, "ADSBRIDGE_ATTRIBUTION_COOKIE")
        else "ll_ads_attr"
    )
    client.cookies[cookie_name] = signed_cookie
    _log("Attribution cookie primed", gclid=gclid)

    unique_email = f"ads-e2e-live+{uuid.uuid4().hex[:8]}@example.com"
    lead_payload = {
        "form_kind": "contact_full",
        "email": unique_email,
        "first_name": "Ads",
        "last_name": "Bridge",
        "consent": True,
        "context": {"scenario": "ads-e2e-live"},
    }

    sign_response = client.post(
        "/api/leads/sign/",
        data=json.dumps({"payload": lead_payload}),
        content_type="application/json",
    )
    if sign_response.status_code != 200:
        raise RuntimeError("Unable to obtain signed token")
    lead_payload["signed_token"] = sign_response.json()["signed_token"]

    idem_key = f"ads-e2e-live-{uuid.uuid4().hex}"
    create_response = client.post(
        "/api/leads/collect/",
        data=json.dumps(lead_payload),
        content_type="application/json",
        HTTP_X_IDEMPOTENCY_KEY=idem_key,
    )
    if create_response.status_code != 202:
        raise RuntimeError(
            f"Lead submission failed: {create_response.status_code} {create_response.content}"
        )
    lead_id = create_response.json()["lead_id"]
    _log("Lead collected", lead_id=lead_id)

    lead = Lead.objects.get(id=lead_id)
    lead.refresh_from_db()

    lead_record = ConversionRecord.objects.get(
        kind=ConversionRecord.Kind.LEAD,
        lead_id=str(lead_id),
    )
    lead_record.refresh_from_db()
    mode = ads_conf.current_mode()
    _log("ADS mode resolved", mode=mode)

    if lead_record.status == ConversionRecord.Status.ERROR:
        _raise_with_payload(lead_record, "Lead")
    if lead_record.status != ConversionRecord.Status.SENT:
        raise RuntimeError(
            f"Lead conversion unexpected status: {lead_record.status}"
        )

    lead_payload_status = lead_record.google_upload_status or {}
    _log(
        "Lead conversion sent",
        record_id=lead_record.id,
        payload_status=lead_payload_status.get("status", "SENT"),
    )

    order = Order.objects.create(
        email=lead.email,
        amount_subtotal=25000,
        tax_amount=0,
        amount_total=25000,
        currency="EUR",
        status=OrderStatus.PENDING,
        idempotency_key=f"order-live-{uuid.uuid4().hex}",
    )
    lead.order = order
    lead.save(update_fields=["order"])

    entitlement_payload = {
        "data": {
            "object": {
                "metadata": {"order_id": str(order.id)},
                "amount_received": order.amount_total,
                "currency": order.currency.lower(),
            }
        }
    }
    EntitlementService.grant_entitlement(
        order,
        "payment_intent.succeeded",
        entitlement_payload,
    )

    purchase_record = ConversionRecord.objects.filter(
        kind=ConversionRecord.Kind.PURCHASE,
        order_id=str(order.id),
    ).latest("id")
    purchase_record.refresh_from_db()
    if purchase_record.status == ConversionRecord.Status.ERROR:
        _raise_with_payload(purchase_record, "Purchase")
    if purchase_record.status != ConversionRecord.Status.SENT:
        raise RuntimeError(
            f"Purchase conversion unexpected status: {purchase_record.status}"
        )
    _log(
        "Purchase conversion sent",
        record_id=purchase_record.id,
        payload_status=(purchase_record.google_upload_status or {}).get("status"),
    )

    refund_event = {
        "type": "charge.refunded",
        "data": {"object": {"metadata": {"order_id": str(order.id)}}},
    }
    _process_event(refund_event)

    adjustment_record = ConversionRecord.objects.filter(
        kind=ConversionRecord.Kind.ADJUSTMENT,
        order_id=str(order.id),
    ).latest("id")
    adjustment_record.refresh_from_db()
    if adjustment_record.status == ConversionRecord.Status.ERROR:
        _raise_with_payload(adjustment_record, "Adjustment")
    if adjustment_record.status != ConversionRecord.Status.SENT:
        raise RuntimeError(
            f"Adjustment conversion unexpected status: {adjustment_record.status}"
        )
    _log(
        "Adjustment conversion sent",
        record_id=adjustment_record.id,
        payload_status=(adjustment_record.google_upload_status or {}).get("status"),
    )

    _log(
        "Live validation complete",
        lead_record=lead_record.id,
        purchase_record=purchase_record.id,
        adjustment_record=adjustment_record.id,
    )
