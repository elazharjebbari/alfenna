"""Business hooks to create conversion records from domain events."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Mapping

from django.db import transaction
from django.utils import timezone

from apps.adsbridge import conf as ads_conf, services
from apps.adsbridge.models import ConversionRecord
from apps.adsbridge.tasks import enqueue_conversion

logger = logging.getLogger("adsbridge")


def record_lead_conversion(lead) -> ConversionRecord | None:
    """Create or reuse a conversion record for a validated lead."""

    attribution = _extract_attribution(getattr(lead, "context", {}))
    consent = bool(getattr(lead, "consent", False))
    enhanced = services.build_enhanced_identifiers(
        email=lead.email,
        phone=lead.phone,
        first_name=lead.first_name,
        last_name=lead.last_name,
    ) if consent else {}

    return _upsert_record(
        kind=ConversionRecord.Kind.LEAD,
        action_key="lead_submit",
        business_reference=f"lead-{lead.id}",
        attribution=attribution,
        event_at=getattr(lead, "created_at", timezone.now()),
        value=None,
        currency=getattr(lead, "currency", None) or services.load_ads_config().default_currency,
        order_id=str(getattr(lead, "order_id", "")) or None,
        lead_id=str(lead.id),
        enhanced_identifiers=enhanced,
        consent=consent,
    )


def record_order_purchase(order, payload: Mapping[str, Any] | None = None) -> ConversionRecord | None:
    """Create a conversion record after a successful purchase."""

    lead = _select_lead_for_order(order)
    consent = bool(getattr(lead, "consent", False)) if lead else False
    attribution = _extract_attribution(getattr(lead, "context", {})) if lead else {}

    enhanced = {}
    if consent and lead:
        enhanced = services.build_enhanced_identifiers(
            email=lead.email or order.email,
            phone=lead.phone,
            first_name=lead.first_name,
            last_name=lead.last_name,
        )

    amount_decimal = None
    if getattr(order, "amount_total", None) is not None:
        amount_decimal = Decimal(order.amount_total or 0) / Decimal(100)

    return _upsert_record(
        kind=ConversionRecord.Kind.PURCHASE,
        action_key="purchase",
        business_reference=f"order-{order.id}",
        attribution=attribution,
        event_at=getattr(order, "updated_at", timezone.now()),
        value=amount_decimal,
        currency=(order.currency or services.load_ads_config().default_currency).upper(),
        order_id=str(order.id),
        lead_id=str(lead.id) if lead else None,
        enhanced_identifiers=enhanced,
        consent=consent,
    )


def record_order_refund(order, payload: Mapping[str, Any] | None = None) -> ConversionRecord | None:
    lead = _select_lead_for_order(order)
    consent = bool(getattr(lead, "consent", False)) if lead else False
    attribution = _extract_attribution(getattr(lead, "context", {})) if lead else {}

    return _upsert_record(
        kind=ConversionRecord.Kind.ADJUSTMENT,
        action_key="purchase_adjustment",
        business_reference=f"adjust-{order.id}",
        attribution=attribution,
        event_at=getattr(order, "updated_at", timezone.now()),
        value=None,
        currency=(order.currency or services.load_ads_config().default_currency).upper(),
        order_id=str(order.id),
        lead_id=str(lead.id) if lead else None,
        enhanced_identifiers={},
        consent=consent,
        adjustment_type="RETRACTION",
    )


def _upsert_record(
    *,
    kind: str,
    action_key: str,
    business_reference: str,
    attribution: Mapping[str, Any],
    event_at,
    value: Decimal | None,
    currency: str,
    order_id: str | None,
    lead_id: str | None,
    enhanced_identifiers: dict[str, str],
    consent: bool,
    adjustment_type: str | None = None,
) -> ConversionRecord | None:
    mode_state = ads_conf.describe_mode()
    if not mode_state.tracking:
        logger.info("ads_s2s_mode_off_skip action=%s", action_key)
        return None

    try:
        config = services.load_ads_config()
        action = services.get_conversion_action(action_key)
    except services.AdsConfigError as exc:
        logger.error("adsbridge_config_error action=%s err=%s", action_key, exc)
        return None

    click_field, click_value = _choose_click_from_attribution(attribution)
    idempotency_key = services.build_idempotency_key(
        action_id=action.action_id,
        customer_id=config.customer_id,
        business_reference=business_reference,
        click_id=click_value,
        event_at=event_at,
    )

    consent_status = (
        ConversionRecord.Status.PENDING if consent else ConversionRecord.Status.SKIPPED_NO_CONSENT
    )
    if consent and mode_state.capture:
        consent_status = ConversionRecord.Status.HELD

    defaults = {
        "kind": kind,
        "action_key": action_key,
        "order_id": order_id,
        "lead_id": lead_id,
        "gclid": attribution.get("gclid"),
        "gbraid": attribution.get("gbraid"),
        "wbraid": attribution.get("wbraid"),
        "gclsrc": attribution.get("gclsrc"),
        "value": value,
        "currency": currency,
        "event_at": event_at,
        "enhanced_identifiers": enhanced_identifiers,
        "status": consent_status,
        "hold_reason": ads_conf.hold_reason() if consent and mode_state.capture else "",
        "effective_mode": mode_state.mode,
        "last_error": "" if consent else "NO_CONSENT",
        "adjustment_type": adjustment_type,
    }

    with transaction.atomic():
        record, created = ConversionRecord.objects.get_or_create(
            idempotency_key=idempotency_key,
            defaults=defaults,
        )
        should_enqueue = False
        if not created:
            updates: dict[str, Any] = {}
            for field in ("gclid", "gbraid", "wbraid", "gclsrc"):
                value = defaults[field]
                if value and not getattr(record, field):
                    setattr(record, field, value)
                    updates[field] = value
            if consent and record.status == ConversionRecord.Status.ERROR:
                target_status = consent_status
                if record.status != target_status:
                    record.status = target_status
                    updates["status"] = target_status
                updates["last_error"] = ""
            if consent and enhanced_identifiers and not record.enhanced_identifiers:
                record.enhanced_identifiers = enhanced_identifiers
                updates["enhanced_identifiers"] = enhanced_identifiers
            if consent:
                target_status = consent_status
                if record.status not in {
                    ConversionRecord.Status.SENT,
                    ConversionRecord.Status.SKIPPED_NO_CONSENT,
                }:
                    if record.status != target_status:
                        record.status = target_status
                        updates["status"] = target_status
                    target_hold = defaults["hold_reason"]
                    if record.hold_reason != target_hold:
                        record.hold_reason = target_hold
                        updates["hold_reason"] = target_hold
                    if record.effective_mode != mode_state.mode:
                        record.effective_mode = mode_state.mode
                        updates["effective_mode"] = mode_state.mode
                    if (
                        target_status == ConversionRecord.Status.PENDING
                        and ads_conf.should_enqueue()
                    ):
                        should_enqueue = True
            if updates:
                updates["updated_at"] = timezone.now()
                ConversionRecord.objects.filter(pk=record.pk).update(**updates)
                record.refresh_from_db()
        elif consent:
            if consent_status == ConversionRecord.Status.PENDING and ads_conf.should_enqueue():
                should_enqueue = True
            elif consent_status == ConversionRecord.Status.HELD:
                logger.info(
                    "ads_s2s_capture_held action=%s record_id=%s", action_key, record.id
                )
        if should_enqueue:
            transaction.on_commit(lambda: enqueue_conversion(record.id))
        return record


def _extract_attribution(context: Any) -> dict[str, str]:
    if not isinstance(context, dict):
        return {}
    value = context.get("ads_attribution") or {}
    if not isinstance(value, dict):
        return {}
    return {k: str(value.get(k)).strip() for k in ("gclid", "gbraid", "wbraid", "gclsrc") if value.get(k)}


def _choose_click_from_attribution(attribution: Mapping[str, Any]) -> tuple[str | None, str | None]:
    for field in ("gclid", "gbraid", "wbraid"):
        val = attribution.get(field)
        if val:
            return field, val
    return None, None


def _select_lead_for_order(order) -> Any:
    try:
        from apps.leads.constants import LeadStatus
    except Exception:  # pragma: no cover - defensive
        return None

    qs = getattr(order, "leads", None)
    if qs is None:
        return None
    lead = qs.filter(status=LeadStatus.VALID).order_by("-updated_at").first()
    if lead:
        return lead
    return qs.order_by("-updated_at").first()
