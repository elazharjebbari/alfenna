from __future__ import annotations

from typing import Dict, List

TRANSLATABLE_FIELDS: Dict[str, List[str]] = {
    "footer": [
        "brand",
        "columns.*.title",
        "columns.*.links.*.label",
        "legal.*",
    ],
    "faq": [
        "title",
        "items.*.q",
        "items.*.a",
        "items.*.label",
        "header",
    ],
    "fab": [
        "label",
        "tooltip",
    ],
    "sticky_order": [
        "cta.primary",
        "cta.secondary",
        "note",
        "price.badge",
    ],
}

__all__ = ["TRANSLATABLE_FIELDS"]
