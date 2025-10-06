"""Celery tasks for the Ads bridge."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Callable

from celery import shared_task
from django.conf import settings
from django.db import transaction

from apps.adsbridge import conf as ads_conf, services
from apps.adsbridge.adapters.google_ads import (
    GoogleAdsActionNotFoundError,
    GoogleAdsAdapter,
    GoogleAdsAdapterError,
    GoogleAdsDuplicateError,
    GoogleAdsTransientError,
    MockGoogleAdsAdapter,
)
from apps.adsbridge.models import ConversionRecord

logger = logging.getLogger("adsbridge.tasks")


def _build_error_payload(exc: Exception) -> dict | None:
    payload: dict[str, object] = {}
    code = getattr(exc, "error_code", None)
    detail = getattr(exc, "error_detail", None)
    errors = getattr(exc, "partial_failure_errors", None)
    status_message = getattr(exc, "partial_failure_status_message", None)
    if code:
        payload["error_code"] = code
    if detail:
        payload["error_detail"] = detail
    if errors:
        payload["errors"] = errors
    if status_message:
        payload["status_message"] = status_message
    return payload or None


def enqueue_conversion(record_id: int) -> None:
    """Dispatch conversion processing based on the record kind."""

    if not settings.GADS_ENABLED:
        logger.info("gads_disabled_skip record_id=%s", record_id)
        return

    try:
        record = ConversionRecord.objects.only("id", "kind", "status", "hold_reason").get(id=record_id)
    except ConversionRecord.DoesNotExist:
        logger.warning("conversion_record_missing record_id=%s", record_id)
        return

    mode = ads_conf.current_mode()
    if not ads_conf.tracking_enabled():
        logger.info("ads_s2s_mode_off_skip id=%s mode=%s", record.id, mode)
        return

    if ads_conf.capture_enabled():
        reason = ads_conf.hold_reason() or "Capture mode"
        record.mark_held(reason, mode=mode)
        logger.info("ads_s2s_capture_hold id=%s reason=%s", record.id, reason)
        return

    if record.status in {
        ConversionRecord.Status.SENT,
        ConversionRecord.Status.SKIPPED_NO_CONSENT,
    }:
        logger.debug("conversion_record_complete status=%s id=%s", record.status, record.id)
        return

    task_map: dict[str, Callable[[int], None]] = {
        ConversionRecord.Kind.ADJUSTMENT: upload_adjustment.delay,
        ConversionRecord.Kind.LEAD: upload_click_conversion.delay,
        ConversionRecord.Kind.PURCHASE: upload_click_conversion.delay,
    }
    try:
        dispatch = task_map[record.kind]
    except KeyError:
        logger.error("conversion_unknown_kind id=%s kind=%s", record.id, record.kind)
        return

    dispatch(record.id)


@shared_task(
    bind=True,
    queue="ads",
    autoretry_for=(GoogleAdsTransientError,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 5},
)
def upload_click_conversion(self, record_id: int) -> None:
    if not settings.GADS_ENABLED:
        logger.info("gads_disabled_click_skip id=%s", record_id)
        return

    mode = ads_conf.current_mode()

    with transaction.atomic():
        try:
            record = ConversionRecord.objects.select_for_update().get(id=record_id)
        except ConversionRecord.DoesNotExist:
            logger.warning("conversion_record_missing id=%s", record_id)
            return

        if record.status in {
            ConversionRecord.Status.SENT,
            ConversionRecord.Status.SKIPPED_NO_CONSENT,
        }:
            logger.debug("conversion_record_complete status=%s id=%s", record.status, record.id)
            return

        if ads_conf.capture_enabled():
            reason = ads_conf.hold_reason() or "Capture mode"
            record.mark_held(reason, mode=mode)
            return

        if not ads_conf.tracking_enabled():
            record.mark_error("ads_s2s_mode_off", mode=mode)
            return

        record.increment_attempts(mode=mode)
        action = services.get_conversion_action(record.action_key)
        config = services.load_ads_config()
        click_field, click_value = services.choose_click_identifier(record)
        if not click_value and not record.enhanced_identifiers:
            record.mark_error("missing_click_identifier", mode=mode)
            logger.warning("conversion_missing_identifiers record_id=%s", record.id)
            return

    try:
        adapter = _get_adapter(mode)
    except GoogleAdsAdapterError as exc:
        logger.exception("conversion_adapter_initialisation_failed id=%s", record.id)
        record.mark_error(str(exc), mode=mode)
        return

    customer_id = getattr(adapter, "customer_id", None) or config.customer_id
    if not customer_id:
        record.mark_error("missing_customer_id", mode=mode)
        logger.error("conversion_missing_customer_id id=%s", record.id)
        return

    currency = record.currency or config.default_currency
    try:
        result = adapter.upload_click_conversion(
            customer_id=customer_id,
            action_id=action.action_id,
            click_id_field=click_field,
            click_id=click_value,
            value=record.value,
            currency=currency,
            order_id=record.order_id or record.lead_id or record.idempotency_key,
            event_at=record.event_at,
            enhanced_identifiers=record.enhanced_identifiers or None,
        )
    except GoogleAdsDuplicateError as exc:
        logger.info("conversion_duplicate id=%s msg=%s", record.id, exc)
        record.mark_sent({"status": "DUPLICATE", "detail": str(exc)}, mode=mode)
        return
    except GoogleAdsTransientError as exc:
        logger.warning("conversion_transient_error id=%s error=%s", record.id, exc)
        record.last_error = str(exc)
        record.effective_mode = mode
        record.save(update_fields=["last_error", "effective_mode", "updated_at", "attempt_count"])
        raise
    except GoogleAdsActionNotFoundError as exc:
        customer_id = exc.customer_id or adapter.customer_id
        detail = {
            "resource_name": exc.resource_name,
            "alias": record.action_key,
            "customer_id": customer_id,
        }
        if exc.alias and exc.alias != record.action_key:
            detail["identifier"] = exc.alias
        if exc.status:
            detail["status"] = exc.status
        logger.error(
            "conversion_action_not_found id=%s alias=%s resource=%s status=%s customer=%s",
            record.id,
            record.action_key,
            exc.resource_name,
            detail.get("status", "UNKNOWN"),
            customer_id,
        )
        record.mark_error(
            str(exc),
            mode=mode,
            payload={
                "error_code": "ACTION_NOT_FOUND",
                "error_detail": detail,
            },
        )
        return
    except GoogleAdsAdapterError as exc:
        payload = _build_error_payload(exc)
        if payload:
            logger.error(
                "conversion_adapter_error id=%s code=%s detail=%s status=%s errors=%s",
                record.id,
                payload.get("error_code"),
                payload.get("error_detail"),
                payload.get("status_message"),
                payload.get("errors"),
            )
        else:
            logger.exception("conversion_adapter_error id=%s", record.id)
        record.mark_error(str(exc), mode=mode, payload=payload)
        return

    record.mark_sent(result.payload, mode=mode)
    logger.info("conversion_uploaded id=%s action=%s", record.id, action.key)


@shared_task(
    bind=True,
    queue="ads",
    autoretry_for=(GoogleAdsTransientError,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 5},
)
def upload_adjustment(self, record_id: int) -> None:
    if not settings.GADS_ENABLED:
        logger.info("gads_disabled_adjustment_skip id=%s", record_id)
        return

    mode = ads_conf.current_mode()

    with transaction.atomic():
        try:
            record = ConversionRecord.objects.select_for_update().get(id=record_id)
        except ConversionRecord.DoesNotExist:
            logger.warning("conversion_record_missing id=%s", record_id)
            return

        if record.status in {
            ConversionRecord.Status.SENT,
            ConversionRecord.Status.SKIPPED_NO_CONSENT,
        }:
            logger.debug("conversion_record_complete status=%s id=%s", record.status, record.id)
            return

        if ads_conf.capture_enabled():
            reason = ads_conf.hold_reason() or "Capture mode"
            record.mark_held(reason, mode=mode)
            return

        if not ads_conf.tracking_enabled():
            record.mark_error("ads_s2s_mode_off", mode=mode)
            return

        record.increment_attempts(mode=mode)
        action = services.get_conversion_action(record.action_key)
        config = services.load_ads_config()
        if not record.order_id:
            record.mark_error("missing_order_id_for_adjustment", mode=mode)
            logger.error("conversion_adjustment_missing_order id=%s", record.id)
            return

    try:
        adapter = _get_adapter(mode)
    except GoogleAdsAdapterError as exc:
        logger.exception("conversion_adjustment_adapter_failed id=%s", record.id)
        record.mark_error(str(exc), mode=mode)
        return

    customer_id = getattr(adapter, "customer_id", None) or config.customer_id
    if not customer_id:
        record.mark_error("missing_customer_id", mode=mode)
        logger.error("conversion_adjustment_missing_customer id=%s", record.id)
        return

    try:
        result = adapter.upload_adjustment(
            customer_id=customer_id,
            action_id=action.action_id,
            order_id=record.order_id,
            adjustment_type=record.adjustment_type or "RETRACTION",
            event_at=record.event_at,
            adjusted_value=record.value,
            currency=record.currency or config.default_currency,
        )
    except GoogleAdsDuplicateError as exc:
        logger.info("conversion_adjustment_duplicate id=%s msg=%s", record.id, exc)
        record.mark_sent({"status": "DUPLICATE", "detail": str(exc)}, mode=mode)
        return
    except GoogleAdsTransientError as exc:
        logger.warning("conversion_adjustment_transient id=%s error=%s", record.id, exc)
        record.last_error = str(exc)
        record.effective_mode = mode
        record.save(update_fields=["last_error", "effective_mode", "updated_at", "attempt_count"])
        raise
    except GoogleAdsActionNotFoundError as exc:
        customer_id = exc.customer_id or adapter.customer_id
        detail = {
            "resource_name": exc.resource_name,
            "alias": record.action_key,
            "customer_id": customer_id,
        }
        if exc.alias and exc.alias != record.action_key:
            detail["identifier"] = exc.alias
        if exc.status:
            detail["status"] = exc.status
        logger.error(
            "conversion_action_not_found_adjustment id=%s alias=%s resource=%s status=%s customer=%s",
            record.id,
            record.action_key,
            exc.resource_name,
            detail.get("status", "UNKNOWN"),
            customer_id,
        )
        record.mark_error(
            str(exc),
            mode=mode,
            payload={
                "error_code": "ACTION_NOT_FOUND",
                "error_detail": detail,
            },
        )
        return
    except GoogleAdsAdapterError as exc:
        payload = _build_error_payload(exc)
        if payload:
            logger.error(
                "conversion_adjustment_error id=%s code=%s detail=%s status=%s errors=%s",
                record.id,
                payload.get("error_code"),
                payload.get("error_detail"),
                payload.get("status_message"),
                payload.get("errors"),
            )
        else:
            logger.exception("conversion_adjustment_error id=%s", record.id)
        record.mark_error(str(exc), mode=mode, payload=payload)
        return

    record.mark_sent(result.payload, mode=mode)
    logger.info("conversion_adjustment_uploaded id=%s action=%s", record.id, action.key)


@lru_cache(maxsize=4)
def _get_adapter(mode: str) -> GoogleAdsAdapter:
    if mode == "mock":
        return MockGoogleAdsAdapter()  # type: ignore[return-value]
    if mode == "on":
        return GoogleAdsAdapter()
    raise GoogleAdsAdapterError(f"Google Ads uploads disabled in mode {mode}")
