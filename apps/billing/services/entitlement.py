from __future__ import annotations

import json
import logging
from typing import Any, Mapping

from django.db import transaction
from django.utils import timezone

from apps.billing.models import CustomerProfile, Entitlement, Order, OrderStatus, Payment, PaymentLog
from apps.billing.services.invoice import issue_invoice
from apps.billing.services.order import get_order_service

logger = logging.getLogger("billing.entitlement")


class EntitlementService:
    @staticmethod
    @transaction.atomic
    def grant_entitlement(
        order: Order,
        event_type: str,
        payload: Mapping[str, object],
        context: Mapping[str, Any] | None = None,
    ) -> None:
        order = Order.objects.select_for_update().get(pk=order.pk)
        if order.status == OrderStatus.PAID:
            PaymentLog.objects.create(
                order=order,
                event_type=f"{event_type}/idempotent",
                payload=json.dumps(payload)[:10000],
            )
            return

        data_object = payload.get("data", {}).get("object", {}) if isinstance(payload, Mapping) else {}
        order_service = get_order_service()
        transition_context = dict(context or {})
        transition_context.setdefault("source", "webhook")
        transition_context.setdefault("event_type", event_type)
        order = order_service.mark_payment_succeeded(
            order,
            data_object if isinstance(data_object, Mapping) else {},
            context=transition_context,
        )

        Payment.objects.update_or_create(
            order=order,
            defaults={
                "stripe_payment_intent_id": order.stripe_payment_intent_id,
                "stripe_payment_method_id": str(data_object.get("payment_method", "") if isinstance(data_object, Mapping) else ""),
                "latest_charge_id": str(data_object.get("latest_charge", "") if isinstance(data_object, Mapping) else ""),
                "status": str(data_object.get("status", "succeeded") if isinstance(data_object, Mapping) else "succeeded"),
                "amount_received": int(data_object.get("amount_received") or order.amount_total if isinstance(data_object, Mapping) else order.amount_total),
                "currency": str(data_object.get("currency", order.currency) if isinstance(data_object, Mapping) else order.currency).upper(),
                "idempotency_key": order.idempotency_key,
            },
        )
        PaymentLog.objects.create(
            order=order,
            event_type=event_type,
            payload=json.dumps(payload)[:10000],
        )

        metadata = order.metadata if isinstance(order.metadata, Mapping) else {}
        guest_id = str(metadata.get("guest_id") or "") if isinstance(metadata, Mapping) else ""
        if order.user_id:
            profile = order.customer_profile
            order_service = get_order_service()
            if profile is None:
                profile = order_service.ensure_customer_profile(
                    email=order.email,
                    user=order.user,
                    stripe_customer_id=order.stripe_customer_id or None,
                    guest_id=guest_id or None,
                )
                if order.customer_profile_id != profile.id:
                    Order.objects.filter(pk=order.pk).update(customer_profile=profile, updated_at=timezone.now())
                    order.customer_profile = profile
            else:
                updates: dict[str, Any] = {}
                if not profile.user_id:
                    updates["user"] = order.user
                if updates:
                    CustomerProfile.objects.filter(pk=profile.pk).update(**updates)
                    profile.refresh_from_db()
            if guest_id and order.customer_profile and order.customer_profile.merged_from_guest_id != guest_id:
                order.customer_profile.mark_guest_merge(guest_id)

        try:
            from apps.adsbridge import hooks as adsbridge_hooks  # type: ignore

            adsbridge_hooks.record_order_purchase(order, payload)
        except Exception:  # pragma: no cover - defensive
            logger.exception("adsbridge.purchase_hook.failed", extra={"order_id": order.id})

        try:
            issue_invoice(order, context={"stripe_payload": data_object})
        except Exception:  # pragma: no cover - defensive
            logger.exception("billing.invoice.generate.failed", extra={"order_id": order.id})

        try:
            from apps.messaging.integrations import notify_order_paid  # type: ignore

            notify_order_paid(order)
        except Exception:  # pragma: no cover - defensive
            logger.exception("messaging.notify_order_paid.failed", extra={"order_id": order.id})

        order.refresh_from_db()
        if order.user_id and order.course_id:
            Entitlement.objects.get_or_create(user_id=order.user_id, course_id=order.course_id)
