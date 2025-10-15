"""
Load the pack-cosmetique-naturel fixtures for French and Arabic and verify the result.

Usage:
  python manage.py runscript scripts.load_pack_cosmetique_fixture
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Set, Tuple

from django.core.management import call_command
from django.db import transaction

from apps.catalog.models import Product
from apps.i18n.models import StringTranslation

SLUG = "pack-cosmetique-naturel"
BASE_DIR = Path(__file__).resolve().parent.parent
FIXTURE_FILES = (
    BASE_DIR / "apps" / "catalog" / "fixtures" / "products_pack_cosmetique_naturel.json",
    BASE_DIR / "apps" / "catalog" / "fixtures" / "product_pack_cosmetique_naturel_ar_translations.json",
)


def _load_fixture_data(path: Path) -> list:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _collect_expected_translations(paths: Iterable[Path]) -> Set[Tuple[str, str]]:
    expected: Set[Tuple[str, str]] = set()
    for path in paths:
        data = _load_fixture_data(path)
        for entry in data:
            if entry.get("model") != "i18n.stringtranslation":
                continue
            fields = entry.get("fields", {})
            if fields.get("object_id") != SLUG:
                continue
            field = fields.get("field")
            language = fields.get("language")
            if field and language:
                expected.add((field, language))
    return expected


def _load_fixture(path: Path) -> None:
    call_command("loaddata", str(path))


def _verify_product(expected: dict) -> None:
    if Product.objects.count() != 1:
        raise RuntimeError("Unexpected product count after fixture load.")
    product = Product.objects.get(slug=SLUG)
    for field_name, expected_value in expected.items():
        actual_value = getattr(product, field_name)
        if str(actual_value) != str(expected_value):
            raise RuntimeError(f"Product field '{field_name}' mismatch.")


def _verify_translations(expected: Set[Tuple[str, str]]) -> None:
    queryset = StringTranslation.objects.filter(model_label="catalog.product", object_id=SLUG)
    actual = {(row.field, row.language) for row in queryset}
    if actual != expected:
        missing = expected - actual
        extra = actual - expected
        message_parts = []
        if missing:
            message_parts.append(f"missing translations: {sorted(missing)}")
        if extra:
            message_parts.append(f"unexpected translations: {sorted(extra)}")
        message = "; ".join(message_parts) or "translation mismatch."
        raise RuntimeError(message)


def run(*args) -> None:
    base_fixture = FIXTURE_FILES[0]
    translation_fixture = FIXTURE_FILES[1]
    for fixture in FIXTURE_FILES:
        if not fixture.exists():
            raise FileNotFoundError(f"Fixture not found: {fixture}")

    base_data = _load_fixture_data(base_fixture)
    expected_product_fields = {}
    for entry in base_data:
        if entry.get("model") == "catalog.product" and entry.get("fields", {}).get("slug") == SLUG:
            expected_product_fields = entry["fields"]
            break
    if not expected_product_fields:
        raise RuntimeError("Expected product data not found in base fixture.")

    expected_translations = _collect_expected_translations((translation_fixture,))

    with transaction.atomic():
        products_deleted, _ = Product.objects.all().delete()
        translations_deleted, _ = StringTranslation.objects.filter(model_label="catalog.product").delete()
        print(f"Deleted products: {products_deleted}, translations: {translations_deleted}")
        for fixture in FIXTURE_FILES:
            print(f"Loading fixture: {fixture.relative_to(BASE_DIR)}")
            _load_fixture(fixture)

    _verify_product(
        {
            "slug": expected_product_fields["slug"],
            "name": expected_product_fields["name"],
            "currency": expected_product_fields["currency"],
            "price": expected_product_fields["price"],
            "promo_price": expected_product_fields["promo_price"],
        }
    )
    _verify_translations(expected_translations)

    print("Pack cosmetique fixtures loaded and verified successfully.")
