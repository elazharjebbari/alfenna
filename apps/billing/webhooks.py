from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Mapping

from django.conf import settings
from django.db import transaction
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.billing.models import Order, OrderStatus, WebhookEvent, WebhookEventStatus
from apps.billing.metrics import record_webhook_processed
from apps.billing.services import EntitlementService, get_client, get_order_service, get_refund_service

log = logging.getLogger("billing.webhooks")


@csrf_exempt
@require_POST
def stripe_webhook_view(request: HttpRequest) -> HttpResponse:
    if not getattr(settings, "BILLING_ENABLED", False):
        return HttpResponse(status=204)

    # NOTE: rate-limiting relies on project-wide middleware; add Billing-specific
    # throttling here if a dedicated throttle primitive becomes available.
    client = get_client()
    signature = request.META.get("HTTP_STRIPE_SIGNATURE", "")
    try:
        event = client.construct_event(request.body, signature)
    except Exception:  # pragma: no cover - defensive network path
        log.warning("billing.webhook.signature_invalid")
        return HttpResponseBadRequest("Invalid signature")

    header_name = getattr(settings, "BILLING_REQUEST_ID_HEADER", "HTTP_X_REQUEST_ID")
    correlation_id = request.META.get(header_name, "")
    if not correlation_id:
        correlation_id = uuid.uuid4().hex
    try:
        _process_event(event, correlation_id=correlation_id, stripe_signature=signature)
    except Exception:
        log.exception("billing.webhook.processing_failed", extra={"event_id": event.get("id")})
        return HttpResponse(status=500)
    return HttpResponse(status=200)


def _process_event(event: Mapping[str, object], *, correlation_id: str = "", stripe_signature: str = "") -> None:
    event_id = str(event.get("id") or "")
    event_type = str(event.get("type") or "")
    data_object = event.get("data", {}).get("object", {}) if isinstance(event.get("data"), Mapping) else {}
    context: dict[str, Any] = {
        "event_id": event_id,
        "event_type": event_type,
        "correlation_id": correlation_id,
    }

    with transaction.atomic():
        record, created = WebhookEvent.objects.select_for_update().get_or_create(
            event_id=event_id,
            defaults={
                "event_type": event_type,
                "status": WebhookEventStatus.PENDING,
                "raw_payload": event,
                "correlation_id": correlation_id,
                "stripe_signature": stripe_signature,
            },
        )
        if not created and record.status == WebhookEventStatus.PROCESSED:
            log.debug("billing.webhook.idempotent", extra=context)
            record_webhook_processed(event_type, "duplicate")
            log.info("billing.webhook.duplicate", extra=context)
            return
        record.event_type = event_type
        record.raw_payload = event
        record.correlation_id = correlation_id
        if stripe_signature:
            record.stripe_signature = stripe_signature
        record.status = WebhookEventStatus.PENDING
        record.save(update_fields=["event_type", "raw_payload", "correlation_id", "stripe_signature", "status", "updated_at"])

        order = _resolve_order(data_object)
        if order is None:
            record.status = WebhookEventStatus.SKIPPED
            record.last_error = "order_not_found"
            record.processed_at = timezone.now()
            record.save(update_fields=["status", "last_error", "processed_at", "updated_at"])
            log.warning("billing.webhook.order_missing", extra=context)
            record_webhook_processed(event_type, "skipped")
            return

        try:
            _dispatch_event(order, event_type, event, data_object, context=context)
        except Exception as exc:
            record.status = WebhookEventStatus.FAILED
            record.last_error = str(exc)
            record.processed_at = timezone.now()
            record.save(update_fields=["status", "last_error", "processed_at", "updated_at"])
            record_webhook_processed(event_type, "failed")
            raise
        else:
            record.status = WebhookEventStatus.PROCESSED
            record.last_error = ""
            record.processed_at = timezone.now()
            record.order = order
            record.save(update_fields=["status", "last_error", "processed_at", "order", "updated_at"])
            record_webhook_processed(event_type, "processed")
            success_extra = dict(context)
            success_extra["order_id"] = order.id
            log.info("billing.webhook.processed", extra=success_extra)


def _resolve_order(data_object: Mapping[str, object]) -> Order | None:
    metadata = data_object.get("metadata", {}) if isinstance(data_object, Mapping) else {}
    order_id = metadata.get("order_id") if isinstance(metadata, Mapping) else None

    if order_id:
        try:
            return Order.objects.select_for_update().get(pk=int(order_id))
        except (Order.DoesNotExist, ValueError):
            pass

    payment_intent_id = str(data_object.get("payment_intent") or data_object.get("id") or "")
    if payment_intent_id:
        order = (
            Order.objects.select_for_update()
            .filter(stripe_payment_intent_id=payment_intent_id)
            .first()
        )
        if order:
            return order

    checkout_session_id = str(data_object.get("id") or "")
    if checkout_session_id:
        order = (
            Order.objects.select_for_update()
            .filter(stripe_checkout_session_id=checkout_session_id)
            .first()
        )
        if order:
            return order
    return None


def _dispatch_event(
    order: Order,
    event_type: str,
    event: Mapping[str, object],
    data_object: Mapping[str, object],
    *,
    context: Mapping[str, Any],
) -> None:
    order_service = get_order_service()
    refund_service = get_refund_service()

    if event_type == "checkout.session.completed":
        _handle_checkout_completed(order, data_object)
        return

    if event_type == "payment_intent.succeeded":
        EntitlementService.grant_entitlement(order, event_type, event, context=context)
        return

    if event_type in {"payment_intent.payment_failed", "payment_intent.canceled"}:
        order_service.mark_payment_failed(order, data_object, context=context)
        return

    if event_type in {"charge.refunded", "payment_intent.refunded"}:
        refund_service.mark_succeeded(order, data_object, context=context)
        try:  # pragma: no cover - integration hook
            from apps.adsbridge import hooks as adsbridge_hooks  # type: ignore

            adsbridge_hooks.record_order_refund(order, data_object)
        except Exception:
            log.exception("billing.webhook.adsbridge_refund.failed", extra=context)
        return

    if event_type.startswith("charge.dispute"):
        dispute_extra = dict(context)
        dispute_extra["order_id"] = order.id
        log.warning("billing.webhook.dispute", extra=dispute_extra)
        return

    info_extra = dict(context)
    info_extra["order_id"] = order.id
    log.info("billing.webhook.unhandled", extra=info_extra)


def _handle_checkout_completed(order: Order, data_object: Mapping[str, object]) -> None:
    updates = {}
    session_id = data_object.get("id")
    if session_id and session_id != order.stripe_checkout_session_id:
        updates["stripe_checkout_session_id"] = str(session_id)
    payment_intent = data_object.get("payment_intent")
    if payment_intent and payment_intent != order.stripe_payment_intent_id:
        updates["stripe_payment_intent_id"] = str(payment_intent)
    customer = data_object.get("customer")
    if customer:
        updates["stripe_customer_id"] = str(customer)
        profile = get_order_service().ensure_customer_profile(
            email=order.email,
            user=order.user,
            stripe_customer_id=str(customer),
        )
        if order.customer_profile_id != profile.id:
            updates["customer_profile"] = profile
    if updates:
        updates["updated_at"] = timezone.now()
        Order.objects.filter(pk=order.pk).update(**updates)
        for field, value in updates.items():
            setattr(order, field, value)
