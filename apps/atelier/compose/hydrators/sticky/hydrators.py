from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.http import HttpRequest
from django.urls import resolve
from django.utils.translation import get_language

from apps.catalog.models import Product
from apps.marketing.models.models_pricing import PricePlan
from apps.atelier.i18n.translation_service import TranslationService


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
        "highlights": [],
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


def _translate_currency(code: str, translator: Optional[TranslationService]) -> str:
    if not code:
        return ""
    key = f"currency.{code}"
    if translator is None:
        return code
    return translator.t(key, default=code)


def _collect_features(feature_values: Any, feature_tokens: Any, *, translator: Optional[TranslationService], fallback: Optional[List[str]] = None) -> List[str]:
    features: List[str] = []

    if isinstance(feature_values, (list, tuple)):
        for value in feature_values:
            if isinstance(value, str) and value.strip():
                features.append(value.strip())

    if isinstance(feature_tokens, (list, tuple)):
        for token in feature_tokens:
            token_str = str(token or "").strip()
            if not token_str:
                continue
            lookup = token_str
            if token_str.startswith("t:"):
                lookup = token_str[2:].strip()
            if not lookup:
                continue
            if translator is not None:
                translated = translator.t(lookup, default=lookup)
            else:
                translated = lookup
            features.append(translated)

    if not features and fallback:
        features.extend(fallback)

    return [item for item in features if item]


def buybar_v2(request: HttpRequest, params: Dict[str, Any] | None) -> Dict[str, Any]:
    params = params or {}
    slug = _get_slug_from_request(request, params.get("product_slug", ""))
    payload = _product_payload(slug)

    plan_slug_param = str(params.get("plan_slug") or "").strip()
    plan_data = _plan_payload(plan_slug_param) if plan_slug_param else {
        "plan_found": False,
        "plan_slug": "",
        "plan_title": "",
        "plan_features": [],
        "plan_price": None,
        "plan_old_price": None,
        "plan_currency": "",
    }

    locale = getattr(request, "LANGUAGE_CODE", None) or get_language() or "fr"
    site_version = getattr(request, "site_version", None) or "core"
    translator: Optional[TranslationService] = None
    try:
        translator = TranslationService(locale=locale, site_version=site_version)
    except Exception:
        translator = None

    title_param = params.get("title")
    title: Optional[str] = None
    if isinstance(title_param, str) and title_param.strip():
        title = title_param.strip()
    else:
        title_token = str(params.get("title_token") or "").strip()
        if title_token:
            lookup = title_token[2:].strip() if title_token.startswith("t:") else title_token
            if translator is not None and lookup:
                title = translator.t(lookup, default=lookup)
            elif lookup:
                title = lookup

    title_fallback = str(params.get("title_fallback") or "sticky_order.title_fallback").strip()
    if not title:
        title = payload["product_name"] or plan_data.get("plan_title") or title_fallback

    amount = payload["promo_price"] if payload["promo_price"] else payload["price"]
    original_price = payload["price"] if payload["promo_price"] else None

    plan_price = plan_data.get("plan_price")
    plan_old_price = plan_data.get("plan_old_price")
    if amount is None and plan_price is not None:
        amount = plan_price
        if plan_old_price and plan_old_price > plan_price:
            original_price = plan_old_price
    elif amount is not None and plan_old_price and plan_price and plan_old_price > plan_price:
        # plan gives better reference price if provided explicitly
        original_price = plan_old_price

    currency = payload["currency"] or plan_data.get("plan_currency") or "MAD"
    currency_label = _translate_currency(currency, translator)

    discount_label = params.get("discount_label")
    if discount_label is None:
        discount_label = params.get("online_discount_label")
    discount_label = str(discount_label or "sticky_order.discount_label").strip()

    cta_label = str(params.get("cta_label") or "sticky_order.cta_primary")
    aria_label = str(params.get("aria_label") or "sticky_order.bar_aria_label")
    close_label = str(params.get("close_label") or "sticky_order.close_aria_label")

    feature_values = params.get("features")
    feature_tokens = params.get("feature_tokens")
    fallback_features: List[str] = []
    if payload.get("product_found") and not feature_values and not feature_tokens:
        # reuse plan features only if explicitly requested via plan slug
        fallback_features = plan_data.get("plan_features") or []
    features = _collect_features(feature_values, feature_tokens, translator=translator, fallback=fallback_features)
    if not features and plan_slug_param and plan_data.get("plan_features"):
        features = [str(item) for item in plan_data.get("plan_features") if item]

    return {
        "product_slug": slug,
        "product_found": payload["product_found"],
        "title": title,
        "amount": amount,
        "original_price": original_price,
        "currency": currency,
        "currency_label": currency_label,
        "discount_label": discount_label,
        "cta_label": cta_label,
        "aria_label": aria_label,
        "close_label": close_label,
        "hero_selector": params.get("hero_selector", "#hero"),
        "form_root_selector": params.get("form_root_selector", "[data-ff-root]"),
        "input_selector": params.get("input_selector", "#ff-fullname"),
        "dismiss_days": int(params.get("dismiss_days", 1) or 1),
        "features": features,
        "plan_slug": plan_slug_param,
    }
