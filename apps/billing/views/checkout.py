from __future__ import annotations

import json
import logging
from typing import Any

from django.conf import settings
from django.db import OperationalError, connection
from django.db.migrations.recorder import MigrationRecorder
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.atelier.compose import pipeline, response
from apps.billing.services import PaymentService
from apps.catalog.models.models import Course
from apps.marketing.models.models_pricing import PricePlan

log = logging.getLogger("billing.views.checkout")


@require_POST
def create_checkout_session(request: HttpRequest) -> JsonResponse:
    if not getattr(settings, "BILLING_ENABLED", False):
        return JsonResponse({"detail": "billing_disabled"}, status=503)

    try:
        payload = json.loads(request.body.decode("utf-8")) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid_json"}, status=400)

    price_plan_slug = payload.get("plan_slug") or payload.get("price_plan_slug")
    course_id = payload.get("course_id")
    course_slug = payload.get("course_slug")

    plan = None
    if price_plan_slug:
        plan = get_object_or_404(PricePlan, slug=price_plan_slug, is_active=True)

    course = None
    if course_id:
        course = get_object_or_404(Course, pk=course_id, is_published=True)
    elif course_slug:
        course = get_object_or_404(Course, slug=course_slug, is_published=True)
    if course is None:
        default_slug = getattr(settings, "DEFAULT_CHECKOUT_COURSE_SLUG", "bougies-naturelles")
        if default_slug:
            course = (
                Course.objects.filter(slug=default_slug, is_published=True)
                .only("id", "slug")
                .first()
            )

    user = request.user if request.user.is_authenticated else None
    email = (payload.get("email") or getattr(user, "email", "") or "").strip()
    if not email:
        return JsonResponse({"error": "email_required"}, status=400)

    metadata = {}
    guest_id = request.headers.get("X-Guest-Id") or payload.get("guest_id")
    if guest_id:
        metadata["guest_id"] = guest_id

    coupon = payload.get("coupon") or payload.get("promo_code")
    currency = payload.get("currency") or "EUR"

    try:
        order, intent_payload = PaymentService.create_or_update_order_and_intent(
            user=user,
            email=email,
            currency=currency,
            course=course,
            price_plan=plan,
            plan_slug=price_plan_slug,
            coupon=coupon,
            metadata=metadata,
        )
    except Exception as exc:
        log.exception("billing.checkout.failed", extra={"email": email})
        return JsonResponse({"error": str(exc)}, status=400)

    response_payload: dict[str, Any] = {
        "orderId": order.id,
        "clientSecret": intent_payload.get("client_secret"),
        "publishableKey": intent_payload.get("publishable_key"),
        "paymentIntent": intent_payload.get("payment_intent"),
        "currency": order.currency,
        "amount": order.amount_total,
    }
    return JsonResponse(response_payload, status=200)


@require_GET
def success_view(request: HttpRequest) -> HttpResponse:
    return _render_checkout_page(request, page_id="billing/success")


@require_GET
def cancel_view(request: HttpRequest) -> HttpResponse:
    return _render_checkout_page(request, page_id="billing/cancel")


def _render_checkout_page(request: HttpRequest, *, page_id: str) -> HttpResponse:
    page_ctx = pipeline.build_page_spec(page_id=page_id, request=request, extra={})
    fragments: dict[str, str] = {}
    for slot_id, slot_ctx in (page_ctx.get("slots") or {}).items():
        rendered = pipeline.render_slot_fragment(page_ctx, slot_ctx, request)
        fragments[slot_id] = rendered.get("html", "")
    assets = pipeline.collect_page_assets(page_ctx)
    return response.render_base(page_ctx, fragments, assets, request)


@require_GET
def health_view(request: HttpRequest) -> JsonResponse:
    try:
        recorder = MigrationRecorder(connection)
        billing_qs = recorder.migration_qs.filter(app="billing")
        latest = billing_qs.order_by("-applied").values_list("name", "applied").first()
        migration_info = {
            "applied_count": billing_qs.count(),
            "latest_name": latest[0] if latest else None,
            "latest_applied": latest[1].isoformat() if latest and latest[1] else None,
        }
    except OperationalError:
        migration_info = {"applied_count": 0, "latest_name": None, "latest_applied": None}

    return JsonResponse(
        {
            "enabled": bool(getattr(settings, "BILLING_ENABLED", False)),
            "stripe_configured": bool(getattr(settings, "STRIPE_SECRET_KEY", "")),
            "publishable_key_configured": bool(getattr(settings, "STRIPE_PUBLISHABLE_KEY", "")),
            "invoice_root": getattr(settings, "BILLING_INVOICE_ROOT", "billing/invoices"),
            "migrations": migration_info,
            "timestamp": timezone.now().isoformat(),
        }
    )
