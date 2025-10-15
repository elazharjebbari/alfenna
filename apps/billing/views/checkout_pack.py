from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Iterable

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from apps.billing.services import PackCheckoutService, compute_pack_totals
from apps.catalog.models.models import Product
from apps.billing.views.checkout import create_checkout_session as _legacy_create_checkout

log = logging.getLogger("billing.views.checkout_pack")


def _default_offer(product: Product):
    offers = list(product.offers.all())
    if not offers:
        return None
    offers.sort(key=lambda offer: (not getattr(offer, "is_featured", False), offer.position, offer.id))
    return offers[0]


def _load_payload(request: HttpRequest) -> dict[str, Any] | None:
    if request.body is None:
        return {}
    try:
        raw = request.body.decode("utf-8")
    except (AttributeError, UnicodeDecodeError):
        return None
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _normalize_slugs(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, (list, tuple, set)):
        iterable: Iterable[Any] = value
    else:
        iterable = [value]
    slugs: list[str] = []
    for item in iterable:
        if not item:
            continue
        slug = str(item).strip()
        if not slug:
            continue
        slugs.append(slug)
    return slugs


def _normalize_pack_slug(value: str) -> str:
    slug = (value or "").strip().lower().replace("_", "-")
    if slug.startswith("pack-"):
        slug = slug[5:]
    return slug


def _serialize_line(line: Any) -> dict[str, Any]:
    return {
        "kind": getattr(line, "kind", ""),
        "slug": getattr(line, "slug", ""),
        "title": getattr(line, "title", ""),
        "amount": getattr(line, "amount", 0),
        "currency": getattr(line, "currency", ""),
        "quantity": getattr(line, "quantity", 1),
    }


def _serialize_totals(totals) -> dict[str, Any]:
    payload = {
        "productSlug": getattr(totals, "product_slug", ""),
        "currency": getattr(totals, "currency", ""),
        "subtotal": getattr(totals, "subtotal", 0),
        "discount": getattr(totals, "discount", 0),
        "total": getattr(totals, "total", 0),
        "paymentMode": getattr(totals, "payment_mode", "online"),
        "availableDiscount": getattr(totals, "available_discount", 0),
        "pack": _serialize_line(getattr(totals, "pack", None)),
        "complementaries": [
            _serialize_line(line) for line in getattr(totals, "complementaries", [])
        ],
    }
    # Provide snake_case mirrors for compatibility with legacy code/tests.
    payload.update(
        {
            "product_slug": payload["productSlug"],
            "payment_mode": payload["paymentMode"],
            "available_discount": payload["availableDiscount"],
        }
    )
    return payload


@require_GET
def checkout_pack_view(request: HttpRequest, slug: str):
    product = get_object_or_404(
        Product.objects.prefetch_related("offers", "cross_sells__complementary"),
        slug=slug,
        is_active=True,
    )

    offer = _default_offer(product)
    default_pack_slug = ""
    initial_totals = None
    if offer:
        default_pack_slug = (offer.extra or {}).get("pack_slug") or offer.code or ""
        default_pack_slug = _normalize_pack_slug(default_pack_slug)
        try:
            initial_totals = compute_pack_totals(
                product_slug=product.slug,
                pack_slug=default_pack_slug,
                complementary_slugs=[],
                currency=product.currency,
                payment_mode="online",
            )
        except Exception:
            initial_totals = None

    complementaries = []
    for rel in product.cross_sells.all():
        comp = rel.complementary
        complementaries.append(
            {
                "slug": comp.slug,
                "title": rel.label_override or comp.title,
                "amount": float(comp.promo_price or comp.price or 0),
                "currency": comp.currency or product.currency,
            }
        )

    complementaries_json = json.dumps(complementaries)

    currency_code = (getattr(initial_totals, "currency", None) or product.currency or "MAD").upper()
    initial_totals_data = {
        "subtotal": getattr(initial_totals, "subtotal", 0),
        "discount": getattr(initial_totals, "discount", 0),
        "total": getattr(initial_totals, "total", 0),
    }

    context = {
        "product": product,
        "default_offer": offer,
        "default_pack_slug": default_pack_slug,
        "initial_totals": initial_totals,
        "initial_totals_data": initial_totals_data,
        "complementaries": complementaries_json,
        "currency_code": currency_code,
        "stripe_publishable_key": getattr(settings, "STRIPE_PUBLISHABLE_KEY", ""),
        "preview_url": reverse("billing:preview_totals"),
        "intent_url": reverse("billing:create_payment_intent"),
    }
    return render(request, "billing/checkout_pack.html", context)


@require_POST
def preview_totals_view(request: HttpRequest) -> JsonResponse:
    payload = _load_payload(request)
    if payload is None:
        return JsonResponse({"error": "invalid_json"}, status=400)

    product_slug = str(payload.get("product_slug") or payload.get("productSlug") or "").strip()
    pack_slug = _normalize_pack_slug(str(payload.get("pack_slug") or payload.get("packSlug") or ""))
    if not product_slug or not pack_slug:
        return JsonResponse({"error": "missing_parameters"}, status=400)

    complementary_slugs = _normalize_slugs(payload.get("complementary_slugs") or payload.get("complementarySlugs"))
    payment_mode = str(payload.get("payment_mode") or payload.get("paymentMode") or "online").strip() or "online"
    currency = payload.get("currency")

    try:
        totals = compute_pack_totals(
            product_slug=product_slug,
            pack_slug=pack_slug,
            complementary_slugs=complementary_slugs,
            currency=currency,
            payment_mode=payment_mode,
        )
    except Product.DoesNotExist:
        log.warning(
            "checkout.pack.intent.unknown_product",
            extra={"product_slug": product_slug, "pack_slug": pack_slug},
        )
        return JsonResponse({"error": "unknown_product"}, status=404)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    return JsonResponse(_serialize_totals(totals), status=200)


@require_http_methods(["GET", "POST"])
def create_payment_intent_view(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        cached = request.session.get("checkout_pack_latest_intent")
        if not cached:
            return JsonResponse({"error": "no_intent"}, status=404)
        return JsonResponse(cached, status=200)

    payload = _load_payload(request)
    if payload is None:
        return JsonResponse({"error": "invalid_json"}, status=400)

    checkout_kind = str(payload.get("checkout_kind") or payload.get("checkoutKind") or "").strip().lower()
    auto_detect_pack = payload.get("pack_slug") or payload.get("packSlug")
    log.info("checkout.pack.intent.request %s", payload)
    if checkout_kind not in {"pack", ""} and not auto_detect_pack:
        return _legacy_create_checkout(request)

    if checkout_kind != "pack" and not auto_detect_pack:
        return _legacy_create_checkout(request)

    product_slug = str(payload.get("product_slug") or payload.get("productSlug") or "").strip()
    pack_slug = _normalize_pack_slug(str(payload.get("pack_slug") or payload.get("packSlug") or ""))
    if not product_slug or not pack_slug:
        return JsonResponse({"error": "pack_required"}, status=400)

    complementary_slugs = _normalize_slugs(payload.get("complementary_slugs") or payload.get("complementarySlugs"))
    payment_mode = str(payload.get("payment_mode") or payload.get("paymentMode") or "online").strip() or "online"
    currency = payload.get("currency")
    ff_session_key = payload.get("ff_session_key") or payload.get("ffSessionKey")

    user = request.user if request.user.is_authenticated else None
    email = str(payload.get("email") or getattr(user, "email", "") or "").strip()
    if not email:
        email = f"guest+{uuid.uuid4().hex}@example.invalid"

    try:
        Product.objects.get(slug=product_slug, is_active=True)
    except Product.DoesNotExist:
        log.warning("checkout.pack.intent.product_missing", extra={"product_slug": product_slug})

    metadata_payload: dict[str, Any] = {}
    for key in ("guest_id", "guestId", "lead_id", "leadId"):
        value = payload.get(key)
        if value:
            metadata_payload[key.replace("Id", "_id").replace("guestId", "guest_id")] = str(value)

    extra_metadata = payload.get("metadata")
    if isinstance(extra_metadata, dict):
        metadata_payload.update({str(k): str(v) for k, v in extra_metadata.items()})

    service = PackCheckoutService()
    try:
        order, intent_payload, totals = service.create_or_update_checkout(
            user=user,
            email=email,
            product_slug=product_slug,
            pack_slug=pack_slug,
            complementary_slugs=complementary_slugs,
            currency=currency,
            payment_mode=payment_mode,
            ff_session_key=str(ff_session_key or "") or None,
            metadata=metadata_payload,
            idempotency_fingerprint=str(payload.get("idempotency_key") or payload.get("idempotencyKey") or "") or None,
        )
    except Product.DoesNotExist:
        return JsonResponse({"error": "unknown_product"}, status=404)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception as exc:  # pragma: no cover - defensive safeguard
        log.exception("billing.checkout.pack.intent_failed", extra={"product": product_slug, "pack": pack_slug})
        return JsonResponse({"error": "intent_failed"}, status=500)

    client_secret = intent_payload.get("client_secret") or intent_payload.get("clientSecret") or f"cs_test_{order.pk}"
    publishable_key = getattr(settings, "STRIPE_PUBLISHABLE_KEY", "")

    payload_totals = _serialize_totals(totals)
    response_payload = {
        "orderId": order.id,
        "clientSecret": client_secret,
        "client_secret": client_secret,
        "payment_intent_id": intent_payload.get("id") or intent_payload.get("payment_intent", {}).get("id"),
        "amount": payload_totals.get("total") or totals.total,
        "currency": payload_totals.get("currency") or totals.currency,
    }
    response_payload.update(payload_totals)
    request.session['checkout_pack_latest_intent'] = response_payload
    request.session.modified = True
    return JsonResponse(response_payload, status=200)
