from __future__ import annotations

from typing import Dict

from django.db import transaction

from apps.catalog.models import Product
from apps.i18n.models import StringTranslation
from apps.i18n.utils import build_translation_key, parse_translation_key


@transaction.atomic
def run(locale: str = "fr", site_version: str = "core", **kwargs) -> Dict[str, object]:
    """
    Seed StringTranslation entries for catalog products.

    Usage:
        python manage.py runscript apps.i18n.scripts.seed_product_translations
    """

    created = 0
    updated = 0

    products = (
        Product.objects.filter(is_active=True)
        .prefetch_related(
            "badges",
            "offers",
            "testimonial_media",
            "cross_sells__complementary",
        )
        .order_by("id")
    )

    for product in products:
        def _upsert(field: str, value: str, *, suffix: str | None = None) -> None:
            nonlocal created, updated
            if not isinstance(value, str) or not value.strip():
                return
            key = build_translation_key(product, field, suffix=suffix, site_version=site_version)
            model_label_value, object_id, field_path = parse_translation_key(key)

            obj, created_flag = StringTranslation.objects.update_or_create(
                model_label=model_label_value,
                object_id=object_id,
                field=field_path,
                language=locale,
                defaults={
                    "text": value,
                    "status": "active",
                    "source": "seed",
                },
            )
            if created_flag:
                created += 1
            else:
                updated += 1

        _upsert("name", product.name or "")
        _upsert("subname", product.subname or "")
        _upsert("description", product.description or "")

        for idx, text in enumerate(product.highlights or []):
            _upsert("highlights", str(text), suffix=str(idx))

        for idx, badge in enumerate(product.badges.all().order_by("id")):
            _upsert("badges", badge.text or "", suffix=f"{idx}.text")

        for idx, offer in enumerate(product.offers.all().order_by("position", "id")):
            _upsert("offers", offer.title or "", suffix=f"{idx}.title")
            _upsert("offers", offer.savings_label or "", suffix=f"{idx}.savings_label")

        for idx, testimonial in enumerate(
            product.testimonial_media.all().order_by("position", "id")
        ):
            _upsert("testimonials", testimonial.author or "", suffix=f"{idx}.author")
            _upsert("testimonials", testimonial.quote or "", suffix=f"{idx}.quote")

        for idx, relation in enumerate(product.cross_sells.all()):
            complementary = relation.complementary
            label = relation.label_override or complementary.title
            _upsert("cross_sells", label or "", suffix=f"{idx}.label")
            _upsert("cross_sells", complementary.title or "", suffix=f"{idx}.title")
            _upsert(
                "cross_sells",
                complementary.short_description or "",
                suffix=f"{idx}.short_description",
            )

    return {
        "products": products.count(),
        "created": created,
        "updated": updated,
        "locale": locale,
        "site_version": site_version,
    }
