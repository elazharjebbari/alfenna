"""Diagnostic alignement collectstatic ↔ serveur pour les variantes d'images."""
from __future__ import annotations
import os
from pathlib import Path
from typing import Dict, List

from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage

from apps.common.runscript_harness import binary_harness

SAMPLE_KEYS: List[str] = [
    "images/logo/logo_text_black_200x60.png",
    "images/shape/shape-8.png",
    "images/slider/slider-default.png",
]
FORMATS = ("avif", "webp", "png", "jpg")


def _original_exists(key: str) -> bool:
    bases = getattr(settings, 'STATICFILES_DIRS', []) or []
    for base in bases:
        candidate = Path(base) / key
        if candidate.exists():
            return True
    return False


def _variants_index() -> Dict[str, Dict[str, str]]:
    try:
        return getattr(staticfiles_storage, "variants_index", {}) or {}
    except Exception as exc:
        print(f"[diag_static_consistency] ERROR Unable to load variants_index: {exc}")
        return {}


def _manifest_path() -> str:
    try:
        return staticfiles_storage.path(staticfiles_storage.manifest_name)
    except Exception as exc:
        return f"<unavailable: {exc}>"


def _storage_path(rel: str) -> str:
    try:
        return staticfiles_storage.path(rel)
    except Exception as exc:
        return f"<unavailable: {exc}>"


@binary_harness
def run() -> Dict[str, object]:
    issues: List[str] = []

    print("[diag_static_consistency] DJANGO_SETTINGS_MODULE:", os.getenv("DJANGO_SETTINGS_MODULE", "<unset>"))
    print("[diag_static_consistency] STATIC_URL:", settings.STATIC_URL)
    print("[diag_static_consistency] STATIC_ROOT:", settings.STATIC_ROOT)
    print(
        "[diag_static_consistency] staticfiles_storage:",
        f"{staticfiles_storage.__class__.__module__}.{staticfiles_storage.__class__.__name__}",
    )
    print("[diag_static_consistency] manifest path:", _manifest_path())

    variants_index = _variants_index()
    print(f"[diag_static_consistency] variants_index entries: {len(variants_index)}")

    for key in SAMPLE_KEYS:
        mapping = variants_index.get(key) or {}
        original_present = _original_exists(key)
        print(f"  - {key} → formats: {sorted(mapping)}")
        if not mapping:
            if original_present:
                issues.append(f"Manifest missing key: {key}")
            else:
                print(f"      - original missing under STATICFILES_DIRS")
            continue
        for fmt in FORMATS:
            rel = mapping.get(fmt)
            if not rel:
                continue
            rel = rel.lstrip("/")
            try:
                storage_has = staticfiles_storage.exists(rel)
            except Exception as exc:
                storage_has = False
                issues.append(f"exists() raised for {rel}: {exc}")
            path = _storage_path(rel)
            disk_has = False
            if not path.startswith("<unavailable"):
                disk_has = Path(path).exists()
            else:
                issues.append(f"No filesystem path for {rel}: {path}")
            print(
                f"      - {fmt}: rel={rel} storage_exists={storage_has} disk_exists={disk_has} path={path}"
            )
            if storage_has and disk_has:
                continue
            issues.append(f"Mismatch for {rel} (storage={storage_has}, disk={disk_has})")

    if issues:
        print("[diag_static_consistency] WARNING mismatches detected:")
        for item in issues:
            print(f"    - {item}")
        print(
            "[diag_static_consistency] Hint: rerun collectstatic --clear with the same DJANGO_SETTINGS_MODULE"
        )

    return {"ok": not issues, "issues": issues}
