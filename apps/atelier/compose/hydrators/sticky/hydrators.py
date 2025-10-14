from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional

from django.http import HttpRequest
from django.urls import resolve

from apps.catalog.models import Product
from apps.marketing.models.models_pricing import PricePlan


def _get_slug_from_request(request: HttpRequest, fallback: str = "") -> str:
    if request is None:
        return fallback.strip()
    resolver_match = getattr(request, "resolver_match", None)
    if resolver_match and getattr(resolver_match, "kwargs", None):
        slug = resolver_match.kwargs.get("product_slug") or resolver_match.kwargs.get("slug")
        if slug:
            return str(slug).strip()
    try:
        match = resolve(request.path_info)
        slug = match.kwargs.get("product_slug") or match.kwargs.get("slug") or fallback
    except Exception:
        slug = fallback
    return str(slug or "").strip()


def _product_payload(slug: str) -> Dict[str, Any]:
    ctx: Dict[str, Any] = {
        "product_found": False,
        "product_name": "",
        "price": None,
        "promo_price": None,
        "currency": "MAD",
    }
    if not slug:
        return ctx
    try:
        product = Product.objects.only("name", "price", "promo_price", "currency").get(slug=slug)
    except Product.DoesNotExist:
        return ctx

    ctx["product_found"] = True
    ctx["product_name"] = (product.name or "").strip()
    if getattr(product, "promo_price", None) is not None:
        ctx["promo_price"] = float(product.promo_price)
    if getattr(product, "price", None) is not None:
        ctx["price"] = float(product.price)
    ctx["currency"] = (getattr(product, "currency", None) or "MAD").strip() or "MAD"
    return ctx


def _to_amount(value: Optional[int]) -> Optional[float]:
    if value in (None, "", 0):
        return None
    try:
        cents = int(value)
    except (TypeError, ValueError):
        return None
    return float(Decimal(cents) / Decimal("100"))


def _plan_payload(plan_slug: str | None) -> Dict[str, Any]:
    queryset = PricePlan.objects.filter(is_active=True)
    plan = None
    slug = (plan_slug or "").strip()
    if slug:
        plan = queryset.filter(slug=slug).first()
    if plan is None:
        plan = queryset.filter(is_featured=True).order_by("display_order", "priority", "id").first()
    if plan is None:
        plan = queryset.order_by("display_order", "priority", "id").first()

    if plan is None:
        return {
            "plan_found": False,
            "plan_slug": "",
            "plan_title": "",
            "plan_features": [],
            "plan_price": None,
            "plan_old_price": None,
            "plan_currency": "",
        }

    return {
        "plan_found": True,
        "plan_slug": plan.slug,
        "plan_title": plan.title,
        "plan_features": list(plan.features or []),
        "plan_price": _to_amount(plan.price_cents),
        "plan_old_price": _to_amount(plan.old_price_cents),
        "plan_currency": plan.get_currency(),
    }


def buybar_v2(request: HttpRequest, params: Dict[str, Any] | None) -> Dict[str, Any]:
    params = params or {}
    slug = _get_slug_from_request(request, params.get("product_slug", ""))
    payload = _product_payload(slug)
    plan_data = _plan_payload(params.get("plan_slug"))

    title_fallback = str(params.get("title_fallback") or "sticky_order.title_fallback").strip()
    title = payload["product_name"] or plan_data.get("plan_title") or title_fallback

    amount = payload["promo_price"] if payload["promo_price"] else payload["price"]
    original_price = payload["price"] if payload["promo_price"] else None

    plan_price = plan_data.get("plan_price")
    plan_old_price = plan_data.get("plan_old_price")
    if plan_price is not None:
        amount = plan_price
        if plan_old_price and plan_old_price > plan_price:
            original_price = plan_old_price
        elif plan_old_price and amount and plan_old_price > amount:
            original_price = plan_old_price
    currency = plan_data.get("plan_currency") or payload["currency"] or "MAD"

    discount_label = params.get("discount_label")
    if discount_label is None:
        # backward compatibility with old key
        discount_label = params.get("online_discount_label")
    discount_label = str(discount_label or "sticky_order.discount_label").strip()

    cta_label = str(params.get("cta_label") or "sticky_order.cta_primary")
    aria_label = str(params.get("aria_label") or "sticky_order.bar_aria_label")
    close_label = str(params.get("close_label") or "sticky_order.close_aria_label")

    return {
        "product_slug": slug,
        "product_found": payload["product_found"],
        "title": title,
        "amount": amount,
        "original_price": original_price,
        "currency": currency,
        "discount_label": discount_label,
        "cta_label": cta_label,
        "aria_label": aria_label,
        "close_label": close_label,
        "hero_selector": params.get("hero_selector", "#hero"),
        "form_root_selector": params.get("form_root_selector", "[data-ff-root]"),
        "input_selector": params.get("input_selector", "#ff-fullname"),
        "dismiss_days": int(params.get("dismiss_days", 1) or 1),
        "plan_title": plan_data.get("plan_title", ""),
        "plan_features": plan_data.get("plan_features") or [],
        "plan_slug": plan_data.get("plan_slug", ""),
    }
