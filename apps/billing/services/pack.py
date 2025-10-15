from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Mapping, Sequence

from django.db import models

from apps.catalog.models.models import Product, ProductOffer
from apps.catalog.models.models_crosssell import ComplementaryProduct, ProductCrossSell

_PACK_PRICE_MAP: dict[str, dict[str, Any]] = {
    "pack-cosmetique-naturel": {
        "currency": "MAD",
        "online_discount_cents": 2000,
        "packs": {
            "solo": {"title": "Pack Solo", "price_cents": 29900},
            "duo": {"title": "Pack Duo", "price_cents": 48900},
        },
        "complementaries": {
            "bougie-massage-hydratante": {
                "title": "+ Bougie de massage hydratante",
                "price_cents": 4000,
            }
        },
    },
}


def _normalize_pack_slug_value(value: str) -> str:
    slug = (value or "").strip().lower().replace("_", "-")
    if slug.startswith("pack-"):
        slug = slug[5:]
    return slug


def _decimal_to_cents(value: Decimal | str | float | int | None) -> int:
    """Convert a decimal monetary value to integer cents."""

    if value is None:
        return 0
    if isinstance(value, int):
        return value * 100
    if isinstance(value, float):
        value = Decimal(str(value))
    if isinstance(value, str):
        value = Decimal(value)
    if not isinstance(value, Decimal):  # defensive fallback
        value = Decimal(value)
    cents = (value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(cents)


@dataclass(frozen=True)
class PackLine:
    kind: str
    slug: str
    title: str
    amount: int
    currency: str
    quantity: int = 1

    def as_metadata(self) -> Mapping[str, str]:
        return {
            "kind": self.kind,
            "slug": self.slug,
            "title": self.title,
            "amount": str(self.amount),
            "currency": self.currency,
            "quantity": str(self.quantity),
        }


@dataclass(frozen=True)
class PackTotals:
    product_slug: str
    currency: str
    pack: PackLine
    complementaries: tuple[PackLine, ...]
    subtotal: int
    discount: int
    total: int
    payment_mode: str
    available_discount: int

    @property
    def complementary_slugs(self) -> tuple[str, ...]:
        return tuple(line.slug for line in self.complementaries)


def _fetch_product(product_slug: str) -> Product:
    lookup = (
        Product.objects.prefetch_related(
            "offers",
            models.Prefetch(
                "cross_sells",
                queryset=ProductCrossSell.objects.select_related("complementary"),
            ),
        )
        .filter(slug=product_slug, is_active=True)
        .first()
    )
    if lookup is None:
        raise Product.DoesNotExist(f"Unknown product slug={product_slug}")
    return lookup


def _resolve_pack_offer(product: Product, pack_slug: str) -> ProductOffer:
    normalized = (pack_slug or "").strip().lower()
    for offer in product.offers.all():
        extra = offer.extra or {}
        extra_slug = str(extra.get("pack_slug") or "").strip().lower()
        if extra_slug and extra_slug == normalized:
            return offer
        if offer.code and offer.code.lower() == normalized:
            return offer
    raise ValueError(f"Unknown pack slug '{pack_slug}' for product '{product.slug}'")


def _resolve_complementary_items(
    product: Product,
    slugs: Sequence[str] | None,
) -> list[tuple[ComplementaryProduct, ProductCrossSell]]:
    requested = [s.strip().lower() for s in (slugs or []) if s]
    if not requested:
        return []

    cross_sells = list(product.cross_sells.all())
    mapping: dict[str, ProductCrossSell] = {}
    for relation in cross_sells:
        comp = relation.complementary
        mapping[comp.slug.lower()] = relation

    resolved: list[tuple[ComplementaryProduct, ProductCrossSell]] = []
    for slug in requested:
        relation = mapping.get(slug)
        if relation is None:
            raise ValueError(f"Unknown complementary slug '{slug}' for product '{product.slug}'")
        resolved.append((relation.complementary, relation))
    return resolved


def _extract_online_discount(product: Product) -> int:
    extra = product.extra or {}
    amount = extra.get("online_discount_amount")
    if not amount:
        ui_texts = extra.get("ui_texts") or {}
        amount = ui_texts.get("online_discount_amount")
    return max(_decimal_to_cents(amount), 0)


def compute_pack_totals(
    *,
    product_slug: str,
    pack_slug: str,
    complementary_slugs: Sequence[str] | None = None,
    currency: str | None = None,
    payment_mode: str = "online",
) -> PackTotals:
    normalized_pack_slug = _normalize_pack_slug_value(pack_slug)
    try:
        product = _fetch_product(product_slug)
        offer = _resolve_pack_offer(product, normalized_pack_slug)
        discount_available = _extract_online_discount(product)
        return _compute_totals_from_product(
            product=product,
            offer=offer,
            pack_slug=normalized_pack_slug,
            complementary_slugs=complementary_slugs,
            currency=currency,
            discount_available=discount_available,
            payment_mode=payment_mode,
        )
    except Product.DoesNotExist:
        mapping = _PACK_PRICE_MAP.get(product_slug)
        if not mapping:
            raise
        return _compute_totals_from_mapping(
            product_slug=product_slug,
            mapping=mapping,
            pack_slug=normalized_pack_slug,
            complementary_slugs=complementary_slugs,
            currency=currency,
            payment_mode=payment_mode,
        )


class PackCheckoutService:
    def __init__(self, order_service=None) -> None:
        from apps.billing.services.order import OrderService, get_order_service

        self.order_service: OrderService = order_service or get_order_service()

    def create_or_update_checkout(
        self,
        *,
        user,
        email: str,
        product_slug: str,
        pack_slug: str,
        complementary_slugs: Sequence[str] | None,
        currency: str | None,
        payment_mode: str,
        ff_session_key: str | None,
        metadata: Mapping[str, str] | None = None,
        idempotency_fingerprint: str | None = None,
    ):
        from apps.billing.services import ItemSpec

        totals = compute_pack_totals(
            product_slug=product_slug,
            pack_slug=pack_slug,
            complementary_slugs=complementary_slugs,
            currency=currency,
            payment_mode=payment_mode,
        )

        metadata_payload = {
            "checkout_kind": "pack",
            "product_slug": totals.product_slug,
            "pack_slug": totals.pack.slug,
            "complementary_slugs": list(totals.complementary_slugs),
            "payment_mode": totals.payment_mode,
            "subtotal_cents": totals.subtotal,
            "discount_cents": totals.discount,
            "total_cents": totals.total,
        }
        if ff_session_key:
            metadata_payload["ff_session_key"] = ff_session_key
        extra_metadata = dict(metadata or {})
        if extra_metadata:
            metadata_payload.update(extra_metadata)

        guest_id = extra_metadata.get("guest_id") or metadata_payload.get("guest_id")

        customer_profile = self.order_service.ensure_customer_profile(
            email=email,
            user=user,
            guest_id=guest_id,
        )

        key = idempotency_fingerprint or (ff_session_key and f"pack:{ff_session_key}")
        if not key:
            import uuid

            key = f"pack:{uuid.uuid4().hex}"

        items: list[ItemSpec] = [
            ItemSpec(
                sku=f"pack:{totals.product_slug}:{totals.pack.slug}",
                quantity=totals.pack.quantity,
                unit_amount=totals.pack.amount,
                description=totals.pack.title,
                metadata={"kind": "pack"},
            )
        ]
        for complementary in totals.complementaries:
            items.append(
                ItemSpec(
                    sku=f"complementary:{complementary.slug}",
                    quantity=complementary.quantity,
                    unit_amount=complementary.amount,
                    description=complementary.title,
                    metadata={"kind": "complementary"},
                )
            )

        order = self.order_service.prepare_order(
            user=user,
            email=email,
            currency=totals.currency,
            amount_subtotal=totals.subtotal,
            tax_amount=0,
            amount_total=totals.total,
            price_plan=None,
            course=None,
            idempotency_key=key,
            metadata=metadata_payload,
            customer_profile=customer_profile,
            items=items,
        )
        order.pricing_code = totals.pack.slug
        order.metadata.update(metadata_payload)
        order.save(update_fields=["pricing_code", "metadata", "updated_at"])

        intent = self.order_service.ensure_payment_intent(
            order,
            idempotency_key=order.idempotency_key,
            metadata=metadata_payload,
        )

        return order, intent, totals


__all__ = [
    "PackCheckoutService",
    "PackLine",
    "PackTotals",
    "compute_pack_totals",
]
def _compute_totals_from_product(
    *,
    product: Product,
    offer: ProductOffer,
    pack_slug: str,
    complementary_slugs: Sequence[str] | None,
    currency: str | None,
    discount_available: int,
    payment_mode: str,
) -> PackTotals:
    preferred_currency = (currency or offer.product.currency or product.currency or "MAD").upper()

    pack_amount_cents = _decimal_to_cents(offer.price)
    pack_line = PackLine(
        kind="pack",
        slug=(offer.extra or {}).get("pack_slug") or offer.code or pack_slug,
        title=offer.title,
        amount=pack_amount_cents,
        currency=preferred_currency,
        quantity=1,
    )

    complementaries: list[PackLine] = []
    for complementary, relation in _resolve_complementary_items(product, complementary_slugs):
        comp_price_source = complementary.promo_price or complementary.price
        amount_cents = _decimal_to_cents(comp_price_source)
        complementaries.append(
            PackLine(
                kind="complementary",
                slug=complementary.slug,
                title=relation.label_override or complementary.title,
                amount=amount_cents,
                currency=complementary.currency or preferred_currency,
                quantity=1,
            )
        )

    subtotal = pack_line.amount + sum(item.amount for item in complementaries)
    normalized_payment_mode = (payment_mode or "online").strip().lower() or "online"
    applied_discount = discount_available if normalized_payment_mode == "online" else 0
    applied_discount = min(subtotal, max(applied_discount, 0))
    total = max(subtotal - applied_discount, 0)

    return PackTotals(
        product_slug=product.slug,
        currency=preferred_currency,
        pack=pack_line,
        complementaries=tuple(complementaries),
        subtotal=subtotal,
        discount=applied_discount,
        total=total,
        payment_mode=normalized_payment_mode,
        available_discount=discount_available,
    )


def _compute_totals_from_mapping(
    *,
    product_slug: str,
    mapping: dict[str, Any],
    pack_slug: str,
    complementary_slugs: Sequence[str] | None,
    currency: str | None,
    payment_mode: str,
) -> PackTotals:
    packs = mapping.get("packs") or {}
    normalized_packs = {_normalize_pack_slug_value(k): v for k, v in packs.items()}
    pack_def = normalized_packs.get(pack_slug)
    if not pack_def:
        raise ValueError(f"Unknown pack slug '{pack_slug}' for product '{product_slug}'")

    preferred_currency = (currency or mapping.get("currency") or "MAD").upper()
    pack_amount_cents = int(pack_def.get("price_cents") or 0)
    pack_line = PackLine(
        kind="pack",
        slug=pack_slug,
        title=pack_def.get("title") or pack_slug,
        amount=pack_amount_cents,
        currency=preferred_currency,
    )

    complementaries_map = mapping.get("complementaries") or {}
    normalized_complementaries = {_normalize_pack_slug_value(k): v for k, v in complementaries_map.items()}
    complementaries: list[PackLine] = []
    for slug in complementary_slugs or []:
        normalized_slug = _normalize_pack_slug_value(slug)
        entry = normalized_complementaries.get(normalized_slug)
        if entry is None:
            raise ValueError(f"Unknown complementary slug '{slug}' for product '{product_slug}'")
        amount_cents = int(entry.get("price_cents") or 0)
        complementaries.append(
            PackLine(
                kind="complementary",
                slug=normalized_slug,
                title=entry.get("title") or slug,
                amount=amount_cents,
                currency=preferred_currency,
            )
        )

    subtotal = pack_line.amount + sum(item.amount for item in complementaries)
    normalized_payment_mode = (payment_mode or "online").strip().lower() or "online"
    discount_available = int(mapping.get("online_discount_cents") or 0)
    applied_discount = discount_available if normalized_payment_mode == "online" else 0
    applied_discount = min(subtotal, max(applied_discount, 0))
    total = max(subtotal - applied_discount, 0)

    return PackTotals(
        product_slug=product_slug,
        currency=preferred_currency,
        pack=pack_line,
        complementaries=tuple(complementaries),
        subtotal=subtotal,
        discount=applied_discount,
        total=total,
        payment_mode=normalized_payment_mode,
        available_discount=discount_available,
    )
