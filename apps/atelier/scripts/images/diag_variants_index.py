"""Diagnostic rapide sur l'index des variantes d'images."""
from __future__ import annotations
from pathlib import Path
from typing import Dict, List

from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage

SAMPLE_KEYS: List[str] = [
    "images/shape/shape-8.png",
    "images/slider/slider-default.png",
]


def _originals_present(keys: List[str]) -> List[str]:
    """Retourne les chemins présents dans le répertoire static/ source."""
    static_dir = Path(getattr(settings, "BASE_DIR", ".")) / "static"
    found: List[str] = []
    for key in keys:
        if (static_dir / key).exists():
            found.append(key)
    return found


def run() -> Dict[str, object]:
    try:
        variants_index = getattr(staticfiles_storage, "variants_index", {}) or {}
    except Exception as exc:  # pragma: no cover - diagnostic
        print(f"[diag_variants_index] WARNING  Impossible de lire variants_index: {exc}")
        return {"ok": False, "error": str(exc)}

    total_entries = len(variants_index)
    print(f"[diag_variants_index] Entrées dans variants_index: {total_entries}")

    sample_formats: Dict[str, List[str]] = {}
    for key in SAMPLE_KEYS:
        mapping = variants_index.get(key) or {}
        formats = [fmt for fmt in ("avif", "webp", "png", "jpg") if fmt in mapping]
        sample_formats[key] = formats
        if mapping:
            print(f"  - {key}: formats={formats}")
        else:
            print(f"  - {key}: (absent de l'index)")

    originals = _originals_present(SAMPLE_KEYS)
    ok = True
    if not variants_index and originals:
        ok = False
        joined = ", ".join(originals)
        print(
            "[diag_variants_index] ERROR Index vide alors que des sources existent dans static/: "
            f"{joined}"
        )

    return {"ok": ok, "entries": total_entries, "samples": sample_formats}
