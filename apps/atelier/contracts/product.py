"""Contracts for the config-first product component."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from apps.leads.utils.fields_map import normalize_fields_map


def _to_decimal(value: Any) -> Optional[Decimal]:
    """Best-effort conversion to ``Decimal``.

    Returns ``None`` when the incoming value is falsy or cannot be parsed.
    """
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


@dataclass
class Badge:
    icon: str = ""
    text: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_obj(cls, raw: Any) -> "Badge":
        if isinstance(raw, cls):
            return raw
        if isinstance(raw, str):
            return cls(text=raw)
        if not isinstance(raw, dict):
            return cls()
        icon = str(raw.get("icon", "") or "")
        text = str(raw.get("text", "") or "")
        extras = {k: v for k, v in raw.items() if k not in {"icon", "text"}}
        return cls(icon=icon, text=text, extra=extras)

    def as_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {"icon": self.icon, "text": self.text}
        data.update(self.extra)
        return data


@dataclass
class MediaImage:
    src: str = ""
    alt: str = ""
    thumb: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_obj(cls, raw: Any) -> "MediaImage":
        if isinstance(raw, cls):
            return raw
        if not isinstance(raw, dict):
            return cls()
        src = str(raw.get("src", "") or "")
        alt = str(raw.get("alt", "") or "")
        thumb_raw = raw.get("thumb")
        thumb = str(thumb_raw) if thumb_raw not in (None, "") else None
        width = raw.get("width")
        if isinstance(width, str) and width.isdigit():
            width = int(width)
        elif isinstance(width, (int, float)):
            width = int(width)
        else:
            width = None
        height = raw.get("height")
        if isinstance(height, str) and height.isdigit():
            height = int(height)
        elif isinstance(height, (int, float)):
            height = int(height)
        else:
            height = None
        extras = {k: v for k, v in raw.items() if k not in {"src", "alt", "thumb", "width", "height"}}
        return cls(src=src, alt=alt, thumb=thumb, width=width, height=height, extra=extras)

    def as_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "src": self.src,
            "alt": self.alt,
        }
        if self.thumb:
            data["thumb"] = self.thumb
        if self.width is not None:
            data["width"] = self.width
        if self.height is not None:
            data["height"] = self.height
        data.update(self.extra)
        return data


@dataclass
class ProductMeta:
    id: str = ""
    slug: str = ""
    name: str = ""
    subname: str = ""
    description: str = ""
    price: Optional[Decimal] = None
    promo_price: Optional[Decimal] = None
    currency: str = "MAD"
    badges: List[Badge] = field(default_factory=list)
    highlights: List[str] = field(default_factory=list)

    @classmethod
    def from_obj(cls, raw: Any) -> "ProductMeta":
        if isinstance(raw, cls):
            return raw
        if not isinstance(raw, dict):
            return cls()
        price = _to_decimal(raw.get("price"))
        promo_price = _to_decimal(raw.get("promo_price"))
        badges = [Badge.from_obj(b) for b in raw.get("badges", []) or []]
        highlights_raw = raw.get("highlights") or []
        if isinstance(highlights_raw, (list, tuple)):
            highlights = [str(item) for item in highlights_raw if item]
        else:
            highlights = []
        return cls(
            id=str(raw.get("id", "") or ""),
            slug=str(raw.get("slug", "") or ""),
            name=str(raw.get("name", "") or ""),
            subname=str(raw.get("subname", "") or ""),
            description=str(raw.get("description", "") or ""),
            price=price,
            promo_price=promo_price,
            currency=str(raw.get("currency", "MAD") or "MAD"),
            badges=badges,
            highlights=highlights,
        )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "slug": self.slug,
            "name": self.name,
            "subname": self.subname,
            "description": self.description,
            "price": self.price,
            "promo_price": self.promo_price,
            "currency": self.currency,
            "badges": [badge.as_dict() for badge in self.badges],
            "highlights": list(self.highlights),
        }


@dataclass
class FormConfig:
    alias: str = "core/forms/lead_step3"
    action_url: str = "leads:collect"
    fields_map: Dict[str, str] = field(default_factory=normalize_fields_map)
    ui_texts: Dict[str, Any] = field(default_factory=dict)
    offers: List[Dict[str, Any]] = field(default_factory=list)
    bump: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_obj(cls, raw: Any) -> "FormConfig":
        if isinstance(raw, cls):
            return raw
        if not isinstance(raw, dict):
            return cls()
        data = cls()
        if raw.get("alias"):
            data.alias = str(raw["alias"])
        if raw.get("action_url"):
            data.action_url = str(raw["action_url"])
        if raw.get("fields_map"):
            fm = raw.get("fields_map") or {}
            if isinstance(fm, dict):
                data.fields_map = normalize_fields_map(fm)
            else:
                data.fields_map = normalize_fields_map()
        else:
            data.fields_map = normalize_fields_map(data.fields_map)
        if raw.get("ui_texts") and isinstance(raw.get("ui_texts"), dict):
            data.ui_texts = dict(raw.get("ui_texts"))
        if raw.get("offers") and isinstance(raw.get("offers"), list):
            data.offers = [dict(item) for item in raw.get("offers") if isinstance(item, dict)]
        if raw.get("bump") and isinstance(raw.get("bump"), dict):
            data.bump = dict(raw.get("bump"))
        return data

    def as_dict(self) -> Dict[str, Any]:
        return {
            "alias": self.alias,
            "action_url": self.action_url,
            "fields_map": self.fields_map,
            "ui_texts": self.ui_texts,
            "offers": self.offers,
            "bump": self.bump,
        }


@dataclass
class Tracking:
    enabled: bool = True
    events: Dict[str, str] = field(
        default_factory=lambda: {
            "view": "lp_variant_view",
            "media_switch": "product_media_switch",
        }
    )

    @classmethod
    def from_obj(cls, raw: Any) -> "Tracking":
        if isinstance(raw, cls):
            return raw
        data = cls()
        if isinstance(raw, dict):
            if "enabled" in raw:
                data.enabled = bool(raw.get("enabled"))
            if raw.get("events"):
                events = {
                    str(k): str(v)
                    for k, v in raw.get("events", {}).items()
                    if isinstance(k, str) and v is not None
                }
                if events:
                    data.events = events
        return data

    def as_dict(self) -> Dict[str, Any]:
        return {"enabled": self.enabled, "events": self.events}


@dataclass
class ProductParams:
    product_slug: str = ""
    product_id: str = ""
    lookup: Dict[str, Any] = field(default_factory=dict)
    product: ProductMeta = field(default_factory=ProductMeta)
    media_lightbox: bool = False
    media_images: List[MediaImage] = field(default_factory=list)
    options: Dict[str, Any] = field(default_factory=dict)
    form: FormConfig = field(default_factory=FormConfig)
    tracking: Tracking = field(default_factory=Tracking)
    rtl: str = "auto"
    ui_texts: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, params: Optional[Dict[str, Any]]) -> "ProductParams":
        params = params or {}
        instance = cls()
        product_slug = params.get("product_slug")
        if product_slug:
            instance.product_slug = str(product_slug)
        product_id = params.get("product_id")
        if product_id:
            instance.product_id = str(product_id)
        lookup_raw = params.get("lookup")
        if isinstance(lookup_raw, dict):
            instance.lookup = dict(lookup_raw)
        if "product" in params:
            instance.product = ProductMeta.from_obj(params.get("product"))
        if "media" in params:
            media_cfg = params.get("media") or {}
            if isinstance(media_cfg, dict):
                instance.media_lightbox = bool(media_cfg.get("lightbox"))
                images = media_cfg.get("images") or []
                if isinstance(images, list):
                    instance.media_images = [MediaImage.from_obj(img) for img in images]
        if "options" in params and isinstance(params.get("options"), dict):
            instance.options = params["options"]  # shallow copy acceptable
        if "form" in params:
            instance.form = FormConfig.from_obj(params.get("form"))
        if "tracking" in params:
            instance.tracking = Tracking.from_obj(params.get("tracking"))
        if params.get("rtl") in {"auto", "on", "off"}:
            instance.rtl = str(params["rtl"])
        if params.get("ui_texts") and isinstance(params.get("ui_texts"), dict):
            instance.ui_texts = dict(params.get("ui_texts"))
        return instance

    def as_dict(self) -> Dict[str, Any]:
        return {
            "product_slug": self.product_slug,
            "product_id": self.product_id,
            "lookup": dict(self.lookup),
            "product": self.product.as_dict(),
            "media": {
                "lightbox": self.media_lightbox,
                "images": [img.as_dict() for img in self.media_images],
            },
            "options": self.options,
            "form": self.form.as_dict(),
            "tracking": self.tracking.as_dict(),
            "rtl": self.rtl if self.rtl in {"auto", "on", "off"} else "auto",
            "ui_texts": self.ui_texts,
        }
