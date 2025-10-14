"""Structured smoke test for the product page (FR site version)."""

from __future__ import annotations

from typing import Dict, List

from django.core.management import call_command
from django.test import Client

from apps.catalog.models import Product
from apps.marketing.models.models_pricing import PricePlan



NAME = "pages.product_page_fr_smoke"
TARGET_URL = "/produits/pack-cosmetique-naturel/"


def _count_occurrences(content: str, needle: str) -> int:
    return content.count(needle)


def run() -> Dict[str, object]:
    if not Product.objects.filter(slug="pack-cosmetique-naturel").exists():
        call_command("loaddata", "alfenna/fixtures/product_pack_cosmetique_naturel.json", verbosity=0)

    plan, _ = PricePlan.objects.get_or_create(
        slug="createur",
        defaults={
            "title": "TITRE_DB_SENTINEL",
            "currency": "MAD",
            "currency_symbol": "MAD",
            "price_cents": 32900,
            "is_active": True,
        },
    )
    if plan.title != "TITRE_DB_SENTINEL":
        plan.title = "TITRE_DB_SENTINEL"
        plan.features = ["FEATURE_DB_SENTINEL"]
        plan.save(update_fields=["title", "features"])

    client = Client()
    response = client.get(TARGET_URL, follow=True, HTTP_ACCEPT_LANGUAGE="fr")
    status_code = response.status_code
    content = response.content.decode("utf-8", errors="ignore")

    gallery_marker = max(
        _count_occurrences(content, "pack-detail-"),
        _count_occurrences(content, "swiper-slide"),
    )

    counts = {
        "status_code": status_code,
        "gallery_items": gallery_marker,
        "faq_slot": _count_occurrences(content, 'data-ll-slot-id="faq"'),
        "testimonials": _count_occurrences(content, "testimonial"),
        "sticky_buybar": _count_occurrences(content, "data-ll-slot-id=\"sticky_buybar"),
    }

    logs: List[str] = []
    if status_code != 200:
        logs.append(f"unexpected status_code={status_code}")
    if counts["gallery_items"] == 0:
        logs.append("gallery empty")
    if counts["sticky_buybar"] == 0:
        logs.append("sticky buybar missing")
    if "TITRE_DB_SENTINEL" not in content:
        logs.append("price plan sentinel missing")

    ok = not logs

    return {
        "ok": ok,
        "name": NAME,
        "counts": counts,
        "logs": logs or ["product smoke OK"],
        "url": TARGET_URL,
    }
