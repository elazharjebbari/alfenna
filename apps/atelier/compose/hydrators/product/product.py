"""Hydrator for the config-first product component."""
from __future__ import annotations

import base64
import json
import logging
from decimal import Decimal, InvalidOperation
from html import escape
from typing import Any, Dict, Iterable, List, Optional, cast

from django.conf import settings
from django.http import HttpRequest
from django.urls import NoReverseMatch, reverse
from django.utils.translation import get_language

from apps.atelier.components.registry import NamespaceComponentMissing, get as get_component
from apps.atelier.components.utils import split_alias_namespace
from apps.atelier.contracts.product import ProductParams
from apps.atelier.i18n.translation_service import TranslationService
from apps.catalog.models import Product as CatalogProduct
from apps.leads.constants import FormKind
from apps.leads.utils.fields_map import normalize_fields_map
from apps.i18n.utils import build_translation_key

logger = logging.getLogger(__name__)

_REQUIRED_FORM_KEYS: Iterable[str] = ("fullname", "phone")


def _svg_placeholder(width: int, height: int, text: str, *, bg: str = "#f5f7fa", fg: str = "#94a3b8") -> str:
    label = escape((text or "").strip() or "Img")
    font_size = max(16, min(width, height) // 4)
    svg = (
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' viewBox='0 0 {width} {height}'>"
        f"<rect width='100%' height='100%' fill='{bg}'/>"
        f"<text x='50%' y='50%' fill='{fg}' font-family='sans-serif' font-size='{font_size}' text-anchor='middle'"
        f" dominant-baseline='central'>{label}</text>"
        "</svg>"
    )
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")


def _resolve_action_url(raw: str) -> str:
    if not raw:
        return ""
    raw = str(raw)
    try:
        return reverse(raw)
    except NoReverseMatch:
        return raw


def _badge_to_dict(badge) -> Dict[str, Any]:
    data = {"icon": badge.icon, "text": badge.text}
    extra = badge.extra or {}
    if isinstance(extra, dict):
        data.update(extra)
    return data


def _normalize_option_items(items: Any) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    if not items:
        return normalized
    for item in items:
        if isinstance(item, dict):
            normalized.append(dict(item))
        else:
            normalized.append({"label": str(item), "value": item})
    return normalized


def _option_to_dict(option) -> Dict[str, Any]:
    data = {
        "key": option.key,
        "label": option.label,
        "enabled": option.enabled,
        "items": _normalize_option_items(option.items or []),
    }
    extra = option.extra or {}
    if isinstance(extra, dict):
        data.update({k: v for k, v in extra.items() if k not in {"key", "label", "items", "enabled"}})
    return data


def _offer_to_dict(offer) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "code": offer.code,
        "title": offer.title,
        "price": offer.price,
        "compare_at_price": offer.compare_at_price,
        "is_featured": offer.is_featured,
        "savings_label": offer.savings_label,
    }
    extra = offer.extra or {}
    if isinstance(extra, dict):
        data.update({k: v for k, v in extra.items() if k not in data})
    return data


def _abs_media_url(request: HttpRequest, url: Any) -> str:
    if not url:
        return ""
    url_str = str(url)
    if url_str.startswith(("http://", "https://", "data:")):
        return url_str
    try:
        return request.build_absolute_uri(url_str)
    except Exception:
        return url_str


def _media_from_db(product, request: HttpRequest) -> List[Dict[str, Any]]:
    images: List[Dict[str, Any]] = []
    fallback_alt = product.name or product.slug or "Produit"
    image_qs = getattr(product, "images", None)
    if not image_qs:
        return images

    for index, img in enumerate(image_qs.all()):
        full_src = getattr(img, "src", None) or getattr(img, "url", None)
        if not full_src:
            file_field = getattr(img, "file", None) or getattr(img, "image", None)
            if file_field is not None and hasattr(file_field, "url"):
                full_src = file_field.url

        thumb_src = (
            getattr(img, "thumb", None)
            or getattr(img, "thumb_url", None)
            or getattr(img, "thumbnail", None)
        )
        if not thumb_src:
            thumb_field = getattr(img, "thumb_file", None)
            if thumb_field is not None and hasattr(thumb_field, "url"):
                thumb_src = thumb_field.url

        data: Dict[str, Any] = {
            "index": index,
            "src": _abs_media_url(request, full_src),
            "alt": img.alt or fallback_alt,
            "thumb": _abs_media_url(request, thumb_src or full_src),
        }
        if img.kind:
            data["kind"] = img.kind
        if img.width:
            data["width"] = img.width
        if img.height:
            data["height"] = img.height
        metadata = img.metadata or {}
        if isinstance(metadata, dict):
            for key, value in metadata.items():
                if key not in data:
                    data[key] = value
        images.append(data)
    return images


def _merge_media_images(base: List[Dict[str, Any]], overlay: List[Dict[str, Any]], *, fallback_alt: str) -> List[Dict[str, Any]]:
    if not overlay:
        merged = [dict(item) for item in base]
    else:
        merged = [dict(item) for item in base]
        indexed: Dict[int, Dict[str, Any]] = {}
        extras: List[Dict[str, Any]] = []
        for raw in overlay:
            if not isinstance(raw, dict):
                continue
            idx_value = raw.get("index")
            if isinstance(idx_value, str) and idx_value.isdigit():
                idx = int(idx_value)
            elif isinstance(idx_value, int):
                idx = idx_value
            else:
                extras.append(dict(raw))
                continue
            indexed[idx] = dict(raw)

        for idx, item in indexed.items():
            while len(merged) <= idx:
                merged.append({})
            base_item = dict(merged[idx]) if idx < len(merged) else {}
            base_item.update(item)
            base_item.setdefault("index", idx)
            merged[idx] = base_item

        if extras:
            start = len(merged)
            for offset, item in enumerate(extras):
                item.setdefault("index", start + offset)
                merged.append(item)

    for idx, item in enumerate(merged):
        item.setdefault("index", idx)
        src = item.get("src", "")
        item["src"] = str(src)
        item["thumb"] = item.get("thumb") or item["src"]
        item["alt"] = item.get("alt") or fallback_alt
    return merged


def _translate_value(
    translator: TranslationService,
    instance: CatalogProduct,
    field: str,
    value: Any,
    *,
    suffix: str | None = None,
    site_version: str | None = None,
) -> Any:
    if not isinstance(value, str) or not value:
        return value
    key = build_translation_key(instance, field, suffix=suffix, site_version=site_version)
    return translator.t(key, default=value)


def _translate_product_content(
    translator: TranslationService,
    product_obj: CatalogProduct,
    product_data: Dict[str, Any],
    offers: List[Dict[str, Any]],
    testimonials: List[Dict[str, Any]],
    *,
    site_version: str,
) -> None:
    product_data["name"] = _translate_value(
        translator, product_obj, "name", product_data.get("name"), site_version=site_version
    )
    product_data["subname"] = _translate_value(
        translator,
        product_obj,
        "subname",
        product_data.get("subname"),
        site_version=site_version,
    )
    product_data["description"] = _translate_value(
        translator,
        product_obj,
        "description",
        product_data.get("description"),
        site_version=site_version,
    )

    highlights = product_data.get("highlights") or []
    if isinstance(highlights, list):
        product_data["highlights"] = [
            _translate_value(
                translator,
                product_obj,
                "highlights",
                item,
                suffix=str(idx),
                site_version=site_version,
            )
            for idx, item in enumerate(highlights)
        ]

    badges = product_data.get("badges") or []
    for idx, badge in enumerate(badges):
        if isinstance(badge, dict) and badge.get("text"):
            badge["text"] = _translate_value(
                translator,
                product_obj,
                "badges",
                badge["text"],
                suffix=f"{idx}.text",
                site_version=site_version,
            )

    for idx, offer in enumerate(offers):
        if offer.get("title"):
            offer["title"] = _translate_value(
                translator,
                product_obj,
                "offers",
                offer["title"],
                suffix=f"{idx}.title",
                site_version=site_version,
            )
        if offer.get("savings_label"):
            offer["savings_label"] = _translate_value(
                translator,
                product_obj,
                "offers",
                offer["savings_label"],
                suffix=f"{idx}.savings_label",
                site_version=site_version,
            )

    for idx, testimonial in enumerate(testimonials):
        if testimonial.get("author"):
            testimonial["author"] = _translate_value(
                translator,
                product_obj,
                "testimonials",
                testimonial["author"],
                suffix=f"{idx}.author",
                site_version=site_version,
            )
        if testimonial.get("quote"):
            testimonial["quote"] = _translate_value(
                translator,
                product_obj,
                "testimonials",
                testimonial["quote"],
                suffix=f"{idx}.quote",
                site_version=site_version,
            )


def _coerce_decimal(value: Any) -> Any:
    if value in (None, ""):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        try:
            return Decimal(value)
        except (InvalidOperation, ValueError):
            return value
    return value


def _decimal_to_str(value: Any) -> str:
    if value in (None, "", False):
        return ""
    dec: Optional[Decimal]
    if isinstance(value, Decimal):
        dec = value
    else:
        try:
            dec = Decimal(str(value))
        except (InvalidOperation, ValueError):
            return str(value)
    if dec is None:
        return ""
    try:
        return format(dec.quantize(Decimal("0.01")), "f")
    except (InvalidOperation, ValueError):
        return format(dec, "f")


def _sanitize_lookup_value(value: Any) -> str:
    if value in (None, "", False):
        return ""
    text = str(value).strip()
    if text.startswith("{{") and text.endswith("}}"):
        return ""
    if text.startswith("{%") and text.endswith("%}"):
        return ""
    return text


def _resolve_product_slug(request, params: Dict[str, Any] | None) -> str:
    """Extract the product slug from the request/params with graceful fallbacks."""
    resolver_match = getattr(request, "resolver_match", None)
    if resolver_match and isinstance(getattr(resolver_match, "kwargs", None), dict):
        for key in ("product_slug", "slug"):
            candidate = resolver_match.kwargs.get(key)
            if candidate:
                return _sanitize_lookup_value(candidate)

    attribute_slug = getattr(request, "_product_slug", "")
    if attribute_slug:
        return _sanitize_lookup_value(attribute_slug)

    if isinstance(params, dict):
        product_params = params.get("product")
        if isinstance(product_params, dict):
            param_slug = product_params.get("slug")
            if param_slug:
                return _sanitize_lookup_value(param_slug)

    return ""


def hydrate_product(request, params: Dict[str, Any] | None, *, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Return the rendering context for the product component."""
    cfg = ProductParams.from_dict(params)
    params = params or {}

    product_params_raw = params.get("product") if isinstance(params.get("product"), dict) else {}
    media_params_raw = params.get("media") if isinstance(params.get("media"), dict) else {}
    ui_texts_params_raw = params.get("ui_texts") if isinstance(params.get("ui_texts"), dict) else {}

    lookup_params = cfg.lookup if isinstance(getattr(cfg, "lookup", None), dict) else {}
    lookup_slug = _sanitize_lookup_value(lookup_params.get("slug"))
    lookup_id = lookup_params.get("id")
    lookup_id = _sanitize_lookup_value(lookup_id) if lookup_id is not None else ""

    resolved_slug = _resolve_product_slug(request, params)
    if resolved_slug:
        lookup_slug = resolved_slug

    lang_code = getattr(request, "LANGUAGE_CODE", None) or get_language() or "fr"
    site_version = getattr(request, "site_version", None) or "core"
    db_translator = TranslationService(locale=lang_code, site_version=site_version)

    if not lookup_slug:
        lookup_slug = cfg.product_slug or cfg.product.slug
    if not lookup_id:
        lookup_id = cfg.product_id or cfg.product.id

    lookup_slug = _sanitize_lookup_value(lookup_slug)
    lookup_id = _sanitize_lookup_value(lookup_id)
    if not lookup_slug:
        logger.warning(
            "product.hydrator.missing_slug path=%s lookup_id=%s",
            getattr(request, "path", "-"),
            lookup_id or "-",
        )

    product_obj: Optional[CatalogProduct] = None
    queryset = CatalogProduct.objects.filter(is_active=True).prefetch_related(
        "badges",
        "images",
        "options",
        "offers",
        "testimonial_media",
        "cross_sells__complementary",
    )

    if lookup_slug:
        try:
            product_obj = queryset.get(slug=lookup_slug)
        except CatalogProduct.DoesNotExist:
            logger.warning("product.hydrator.not_found slug=%s", lookup_slug)
            product_obj = None

    if product_obj is None and lookup_id:
        pk_value: Any = lookup_id
        try:
            pk_value = int(str(lookup_id))
        except (TypeError, ValueError):
            pk_value = lookup_id
        try:
            product_obj = queryset.get(pk=pk_value)
        except (CatalogProduct.DoesNotExist, ValueError):
            logger.warning("product.hydrator.not_found_by_id id=%s", lookup_id)
            product_obj = None

    product_data: Dict[str, Any] = {}
    media_images_db: List[Dict[str, Any]] = []
    options_map: Dict[str, Dict[str, Any]] = {}
    offers_db: List[Dict[str, Any]] = []
    testimonials: List[Dict[str, Any]] = []
    cross_sells: List[Dict[str, Any]] = []
    bump_db: Dict[str, Any] = {}
    ui_texts_db: Dict[str, Any] = {}
    media_lightbox_db: Optional[bool] = None

    if product_obj:
        product_data = {
            "id": str(product_obj.pk),
            "slug": product_obj.slug,
            "name": product_obj.name,
            "subname": product_obj.subname,
            "description": product_obj.description,
            "price": product_obj.price,
            "promo_price": product_obj.promo_price,
            "currency": product_obj.currency,
            "badges": [_badge_to_dict(badge) for badge in product_obj.badges.all()],
            "highlights": list(product_obj.highlights or []),
        }
        media_images_db = _media_from_db(product_obj, request)
        options_map = {opt.key: _option_to_dict(opt) for opt in product_obj.options.all()}
        offers_db = [_offer_to_dict(offer) for offer in product_obj.offers.all()]
        testimonials = [
            {
                "author": item.author,
                "quote": item.quote,
                "image_url": item.image_url,
                "video_url": item.video_url,
                "position": item.position,
                **(item.extra or {}),
            }
            for item in product_obj.testimonial_media.all()
        ]
        extra = product_obj.extra or {}
        if isinstance(extra, dict):
            bump_raw = extra.get("bump")
            if isinstance(bump_raw, dict):
                bump_db = dict(bump_raw)
            ui_texts_raw = extra.get("ui_texts")
            if isinstance(ui_texts_raw, dict):
                ui_texts_db = dict(ui_texts_raw)
            if "media_lightbox" in extra:
                media_lightbox_db = bool(extra.get("media_lightbox"))
            elif isinstance(extra.get("media"), dict) and "lightbox" in extra.get("media"):
                media_lightbox_db = bool(extra.get("media").get("lightbox"))

        for relation in product_obj.cross_sells.all():
            complementary = getattr(relation, "complementary", None)
            if not complementary or not complementary.is_active:
                continue
            comp_price = _coerce_decimal(complementary.price)
            comp_promo = _coerce_decimal(complementary.promo_price)
            has_promo = bool(comp_price and comp_promo and comp_promo < comp_price)
            effective_price = comp_promo if has_promo else comp_price
            cross_sells.append(
                {
                    "slug": complementary.slug,
                    "title": complementary.title,
                    "short_description": complementary.short_description,
                    "price": comp_price,
                    "promo_price": comp_promo if comp_promo is not None else None,
                    "effective_price": effective_price,
                    "has_promo": has_promo,
                    "currency": complementary.currency or product_data.get("currency"),
                    "image_src": complementary.image_src,
                    "position": relation.position,
                    "label": relation.label_override or complementary.title,
                    "value": complementary.slug,
                    "extra": dict(complementary.extra or {}),
                }
            )

        _translate_product_content(
            db_translator,
            product_obj,
            product_data,
            offers_db,
            testimonials,
            site_version=site_version,
        )

        for idx, item in enumerate(cross_sells):
            if item.get("label"):
                item["label"] = _translate_value(
                    db_translator,
                    product_obj,
                    "cross_sells",
                    item["label"],
                    suffix=f"{idx}.label",
                    site_version=site_version,
                )
            if item.get("short_description"):
                item["short_description"] = _translate_value(
                    db_translator,
                    product_obj,
                    "cross_sells",
                    item["short_description"],
                    suffix=f"{idx}.short_description",
                    site_version=site_version,
                )
            if item.get("title"):
                item["title"] = _translate_value(
                    db_translator,
                    product_obj,
                    "cross_sells",
                    item["title"],
                    suffix=f"{idx}.title",
                    site_version=site_version,
                )

        if cross_sells and not bump_db:
            primary = min(cross_sells, key=lambda item: item.get("position", 0))
            primary_price = primary.get("effective_price") or primary.get("price")
            bump_db = {
                "enabled": True,
                "value": primary.get("value"),
                "label": primary.get("label"),
                "sublabel": primary.get("short_description"),
                "price": str(primary_price) if primary_price is not None else "",
                "image": primary.get("image_src"),
                "currency": primary.get("currency"),
                "alt": primary.get("title"),
            }

    overlay_product = cfg.product.as_dict()

    if not product_obj:
        if isinstance(product_params_raw, dict) and "id" in product_params_raw:
            product_data["id"] = overlay_product.get("id") or product_data.get("id")
        elif "id" not in product_data and overlay_product.get("id"):
            product_data["id"] = overlay_product.get("id")

        if isinstance(product_params_raw, dict) and "slug" in product_params_raw:
            product_data["slug"] = overlay_product.get("slug") or product_data.get("slug")
        elif "slug" not in product_data:
            if overlay_product.get("slug"):
                product_data["slug"] = overlay_product.get("slug")
            elif lookup_slug:
                product_data["slug"] = lookup_slug

        if isinstance(product_params_raw, dict) and "name" in product_params_raw:
            product_data["name"] = overlay_product.get("name") or product_data.get("name")
        elif "name" not in product_data and overlay_product.get("name"):
            product_data["name"] = overlay_product.get("name")

        if isinstance(product_params_raw, dict) and "subname" in product_params_raw:
            product_data["subname"] = overlay_product.get("subname") or product_data.get("subname")
        elif "subname" not in product_data and overlay_product.get("subname"):
            product_data["subname"] = overlay_product.get("subname")

        if isinstance(product_params_raw, dict) and "description" in product_params_raw:
            product_data["description"] = overlay_product.get("description") or product_data.get("description")
        elif "description" not in product_data and overlay_product.get("description"):
            product_data["description"] = overlay_product.get("description")

        if isinstance(product_params_raw, dict) and "price" in product_params_raw:
            product_data["price"] = overlay_product.get("price")
        elif "price" not in product_data and overlay_product.get("price") is not None:
            product_data["price"] = overlay_product.get("price")

        if isinstance(product_params_raw, dict) and "promo_price" in product_params_raw:
            product_data["promo_price"] = overlay_product.get("promo_price")
        elif "promo_price" not in product_data and overlay_product.get("promo_price") is not None:
            product_data["promo_price"] = overlay_product.get("promo_price")

        if isinstance(product_params_raw, dict) and "currency" in product_params_raw:
            product_data["currency"] = overlay_product.get("currency") or product_data.get("currency")
        elif "currency" not in product_data and overlay_product.get("currency"):
            product_data["currency"] = overlay_product.get("currency")

        if isinstance(product_params_raw, dict) and "badges" in product_params_raw:
            product_data["badges"] = overlay_product.get("badges") or []
        elif "badges" not in product_data:
            product_data["badges"] = overlay_product.get("badges") or []

        if isinstance(product_params_raw, dict) and "highlights" in product_params_raw:
            product_data["highlights"] = list(overlay_product.get("highlights") or [])
        elif "highlights" not in product_data:
            product_data["highlights"] = list(overlay_product.get("highlights") or [])

    product_data.setdefault("id", cfg.product.id or lookup_id or lookup_slug or "product")
    product_data.setdefault("slug", lookup_slug)
    product_data.setdefault("name", cfg.product.name or "Produit")
    if not product_data["name"]:
        product_data["name"] = "Produit"
    product_data.setdefault("subname", cfg.product.subname or "")
    product_data.setdefault("description", cfg.product.description or "")
    if "currency" not in product_data or not product_data["currency"]:
        product_data["currency"] = cfg.product.currency or "MAD"
    product_data.setdefault("badges", [])
    product_data.setdefault("highlights", [])

    product_data["price"] = _coerce_decimal(product_data.get("price"))
    product_data["promo_price"] = _coerce_decimal(product_data.get("promo_price"))

    fallback_alt = product_data.get("name") or "Produit"
    overlay_media = [img.as_dict() for img in cfg.media_images]
    media_images = _merge_media_images(media_images_db, overlay_media, fallback_alt=fallback_alt)
    media_images = [img for img in media_images if img.get("src")]
    if not media_images:
        title_safe = fallback_alt.strip() or "Produit"
        media_images = [
            {
                "index": idx,
                "src": _svg_placeholder(960, 720, f"{title_safe} {idx + 1}"),
                "thumb": _svg_placeholder(176, 132, str(idx + 1), bg="#e2e8f0"),
                "alt": title_safe,
            }
            for idx in range(3)
        ]
    else:
        for idx, item in enumerate(media_images):
            item["index"] = idx
            item_src = _abs_media_url(request, item.get("src"))
            item["src"] = item_src
            thumb_src = item.get("thumb") or item_src
            item["thumb"] = _abs_media_url(request, thumb_src)
            item["alt"] = item.get("alt") or fallback_alt

    media_lightbox = media_lightbox_db if media_lightbox_db is not None else False
    if isinstance(media_params_raw, dict) and "lightbox" in media_params_raw:
        media_lightbox = bool(media_params_raw.get("lightbox"))
    elif cfg.media_lightbox:
        media_lightbox = True

    options_final: Dict[str, Any] = {key: dict(value) for key, value in options_map.items()}
    if isinstance(cfg.options, dict):
        for key, overlay in cfg.options.items():
            if isinstance(overlay, dict):
                base = options_final.get(key, {"key": key})
                merged = dict(base)
                for opt_key, opt_value in overlay.items():
                    if opt_key == "items" and isinstance(opt_value, (list, tuple)):
                        merged["items"] = _normalize_option_items(opt_value)
                    else:
                        merged[opt_key] = opt_value
                merged.setdefault("enabled", True)
                merged.setdefault("label", key.replace("_", " ").title())
                merged.setdefault("items", [])
                options_final[key] = merged
            else:
                options_final[key] = overlay

    offers_lookup = {offer.get("code"): dict(offer) for offer in offers_db if offer.get("code")}
    final_offers: List[Dict[str, Any]] = []
    if cfg.form.offers:
        used_codes: set[str] = set()
        for overlay in cfg.form.offers:
            if not isinstance(overlay, dict):
                continue
            code = str(overlay.get("code") or "").strip()
            base_offer = offers_lookup.get(code) if code else None
            merged = dict(base_offer or {})
            merged.update(overlay)
            if code:
                used_codes.add(code)
            final_offers.append(merged)
        for offer in offers_db:
            code = offer.get("code")
            if code and code in used_codes:
                continue
            final_offers.append(offer)
    else:
        final_offers = offers_db

    for offer in final_offers:
        if isinstance(offer, dict):
            if "price" in offer:
                offer["price"] = _coerce_decimal(offer.get("price"))
            if "compare_at_price" in offer:
                offer["compare_at_price"] = _coerce_decimal(offer.get("compare_at_price"))

    bump_final: Dict[str, Any] = dict(bump_db)
    if cfg.form.bump:
        bump_final.update(cfg.form.bump)

    ui_texts_final: Dict[str, Any] = {}
    ui_texts_final.update(ui_texts_db)
    if ui_texts_params_raw:
        ui_texts_final.update(ui_texts_params_raw)
    if cfg.ui_texts:
        ui_texts_final.update(cfg.ui_texts)
    if cfg.form.ui_texts:
        ui_texts_final.update(cfg.form.ui_texts)
    if ui_texts_final:
        ui_texts_final = cast(Dict[str, Any], db_translator.walk(ui_texts_final))

    form_cfg = cfg.form
    action_url = _resolve_action_url(form_cfg.action_url)
    sign_url = reverse("leads:sign")

    alias_ns, alias_base = split_alias_namespace(form_cfg.alias)
    form_template = None
    if alias_base:
        try:
            meta = get_component(alias_base, namespace=alias_ns)
            form_template = (meta or {}).get("template")
        except NamespaceComponentMissing:
            logger.warning(
                "Form alias '%s' not registered for namespace '%s'", alias_base, alias_ns
            )

    missing_map_keys = [key for key in _REQUIRED_FORM_KEYS if key not in form_cfg.fields_map]
    if missing_map_keys:
        logger.warning(
            "Product component form mapping incomplete; missing keys: %s", ", ".join(missing_map_keys)
        )

    price = product_data.get("price")
    promo = product_data.get("promo_price")
    pricing = {
        "currency": product_data.get("currency"),
        "price": price,
        "promo_price": promo,
        "has_promo": bool(price and promo and promo < price),
        "savings": (price - promo) if (price and promo and price > promo) else None,
    }
    currency_code = pricing.get("currency") or product_data.get("currency")
    currency_label = ""
    if currency_code:
        currency_label = db_translator.t(
            f"currency.{currency_code}", default=str(currency_code)
        )
    if currency_label:
        pricing["currency_label"] = currency_label
        pricing["currency_display"] = currency_label

    language_code = getattr(request, "LANGUAGE_CODE", None) or get_language() or "en"
    lang_prefix = str(language_code).lower()[:2]
    rtl_mode = cfg.rtl if cfg.rtl in {"auto", "on", "off"} else "auto"
    is_rtl = rtl_mode == "on" or (rtl_mode == "auto" and lang_prefix in {"ar", "he", "fa"})

    flow_context = {
        "product_id": product_data.get("id"),
        "product_name": product_data.get("name"),
    }
    if product_data.get("slug"):
        flow_context["product_slug"] = product_data.get("slug")
    if getattr(request, "GET", None):
        for key in ("campaign", "source", "utm_source", "utm_medium", "utm_campaign"):
            value = request.GET.get(key)
            if value:
                flow_context[key] = value

    form_fields_map = normalize_fields_map(form_cfg.fields_map or {})
    form_fields_map.setdefault("wa_optin", "wa_optin")
    default_address_key = form_fields_map.get("address") or "address_raw"
    form_fields_map.setdefault("address", default_address_key)
    form_fields_map.setdefault("address_raw", default_address_key)
    form_fields_map.setdefault("promotion", form_fields_map.get("promotion") or "promotion_selected")

    complementaries_ctx: List[Dict[str, str]] = []
    for item in cross_sells:
        slug = str(item.get("slug") or "").strip()
        if not slug:
            continue
        title = item.get("title") or item.get("label") or slug
        price_value = (
            item.get("effective_price")
            or item.get("promo_price")
            or item.get("price")
        )
        currency_value = (
            item.get("currency")
            or product_data.get("currency")
            or ""
        )
        complementary_entry: Dict[str, str] = {
            "slug": slug,
            "title": str(title),
            "price": _decimal_to_str(price_value),
            "currency": str(currency_value or ""),
        }
        image_src = item.get("image_src")
        if image_src:
            complementary_entry["image_src"] = str(image_src)
        complementaries_ctx.append(complementary_entry)

    if complementaries_ctx:
        flow_context["complementaries"] = complementaries_ctx

    def _filter_fields(values: List[str | None]) -> List[str]:
        seen: set[str] = set()
        filtered: List[str] = []
        for value in values:
            if not value or value in seen:
                continue
            seen.add(value)
            filtered.append(value)
        return filtered

    progress_steps = {
        "step1": _filter_fields(
            [
                form_fields_map.get("first_name"),
                form_fields_map.get("last_name"),
                form_fields_map.get("fullname"),
                form_fields_map.get("email"),
                form_fields_map.get("phone"),
                form_fields_map.get("address_line1"),
                form_fields_map.get("address_line2"),
                form_fields_map.get("city"),
                form_fields_map.get("state"),
                form_fields_map.get("postal_code"),
                form_fields_map.get("country"),
                form_fields_map.get("product"),
                "campaign",
                "source",
                "utm_source",
                "utm_medium",
                "utm_campaign",
                form_fields_map.get("wa_optin"),
            ]
        ),
        "step2": _filter_fields(
            [
                form_fields_map.get("pack_slug"),
                form_fields_map.get("offer"),
                form_fields_map.get("quantity"),
                form_fields_map.get("bump"),
                form_fields_map.get("promotion"),
                form_fields_map.get("address"),
                form_fields_map.get("payment_method"),
                "context.complementary_slugs",
            ]
        ),
    }

    flow_config = {
        "form_kind": FormKind.CHECKOUT_INTENT,
        "flow_key": "checkout_intent_flow",
        "endpoint_url": action_url or reverse("leads:collect"),
        "require_idempotency": True,
        "require_signed_token": True,
        "sign_url": sign_url,
        "progress_url": reverse("leads:progress"),
        "progress_steps": progress_steps,
        "progress_session_field_name": "ff_session_key",
        "progress_flow_field_name": "ff_flow_key",
        "progress_session_storage_key": "ff_session",
        "progress_form_kind": FormKind.CHECKOUT_INTENT,
        "context": flow_context,
        "fields_map": form_fields_map,
    }

    context_out = {
        "product": product_data,
        "pricing": pricing,
        "media": {"lightbox": media_lightbox, "images": media_images},
        "options": options_final,
        "form": {
            "alias": form_cfg.alias,
            "action_url": action_url,
            "fields_map": form_fields_map,
            "template": form_template,
            "ui_texts": ui_texts_final,
            "offers": final_offers,
            "bump": bump_final,
            "flow_key": flow_config["flow_key"],
            "flow_config_json": json.dumps(flow_config, ensure_ascii=False),
        },
        "tracking": cfg.tracking.as_dict(),
        "rtl_mode": rtl_mode,
        "is_rtl": is_rtl,
        "language_prefix": lang_prefix,
        "testimonials": testimonials,
        "cross_sells": cross_sells,
    }

    def _to_float(value: Any) -> Optional[float]:
        if value in (None, ""):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, Decimal):
            return float(value)
        try:
            return float(str(value))
        except (TypeError, ValueError):
            return None

    effective_unit_price = pricing.get("promo_price") if pricing.get("has_promo") else pricing.get("price")
    if effective_unit_price is None:
        effective_unit_price = pricing.get("price") or pricing.get("promo_price")

    online_discount_raw = ui_texts_final.get("online_discount_amount") if isinstance(ui_texts_final, dict) else None
    if not online_discount_raw and isinstance(ui_texts_final, dict):
        online_discount_raw = ui_texts_final.get("online_discount")

    context_out["checkout_hints"] = {
        "unit_price": _to_float(effective_unit_price),
        "base_price": _to_float(pricing.get("price")),
        "promo_price": _to_float(pricing.get("promo_price")),
        "currency": pricing.get("currency") or product_data.get("currency") or "MAD",
        "currency_display": pricing.get("currency_label") or pricing.get("currency_display") or pricing.get("currency") or product_data.get("currency") or "MAD",
        "online_discount": _to_float(online_discount_raw) or 0.0,
        "product_id": product_data.get("id"),
        "product_slug": product_data.get("slug"),
        "product_name": product_data.get("name"),
    }

    for key in ("price", "promo_price", "savings"):
        value = context_out["pricing"].get(key)
        if value is not None:
            try:
                context_out["pricing"][f"{key}_display"] = f"{value:.2f}"
            except (TypeError, ValueError):
                context_out["pricing"][f"{key}_display"] = str(value)

    if settings.DEBUG:
        logger.debug(
            "product.hydrator.context slug=%s product_found=%s media=%d testimonials=%d cross_sells=%d offers=%d",
            lookup_slug or "-",
            bool(product_obj),
            len(media_images_db),
            len(testimonials),
            len(cross_sells),
            len(final_offers),
        )

    return context_out
