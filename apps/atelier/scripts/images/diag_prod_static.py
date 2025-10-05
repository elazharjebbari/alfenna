"""Diagnostic for prod static image variants."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage

from apps.common.runscript_harness import binary_harness

TARGET_KEYS: List[str] = [
    "images/logo/logo_text_black_200x60.png",
    "images/shape/shape-7.png",
    "images/shape/shape-8.png",
    "images/slider/slider-default.png",
]


def _storage_path(rel: str) -> Dict[str, object]:
    rel = rel.lstrip("/")
    exists = False
    exists_error = None
    try:
        exists = staticfiles_storage.exists(rel)
    except Exception as exc:  # pragma: no cover - diagnostic helper
        exists_error = str(exc)

    fs_path = None
    fs_exists = None
    fs_error = None
    try:
        fs_path = staticfiles_storage.path(rel)
        fs_exists = Path(fs_path).exists()
    except Exception as exc:  # pragma: no cover - remote storage or missing path
        fs_error = str(exc)

    return {
        "rel": rel,
        "storage_exists": exists,
        "storage_error": exists_error,
        "fs_path": fs_path,
        "fs_exists": fs_exists,
        "fs_error": fs_error,
    }


@binary_harness
def run() -> Dict[str, object]:  # pragma: no cover - diagnostic script
    print("=== prod static variants diagnostics ===")
    print(f"STATIC_URL: {settings.STATIC_URL}")
    print(f"STATIC_ROOT: {settings.STATIC_ROOT}")
    storage_cfg = getattr(settings, "STORAGES", {}).get("staticfiles", {})
    print(f"STATICFILES_STORAGE: {storage_cfg.get('BACKEND')}")

    manifest_name = getattr(staticfiles_storage, "manifest_name", None)
    manifest_path = None
    manifest_error = None
    if manifest_name:
        try:
            manifest_path = staticfiles_storage.path(manifest_name)
        except Exception as exc:
            manifest_error = str(exc)
    print(f"Manifest name: {manifest_name}")
    if manifest_path:
        print(f"Manifest path: {manifest_path}")
    if manifest_error:
        print(f"Manifest path error: {manifest_error}")

    try:
        variants_index = getattr(staticfiles_storage, "variants_index", {}) or {}
    except Exception as exc:
        print(f"ERROR reading variants_index: {exc}")
        variants_index = {}

    summary: Dict[str, object] = {
        "manifest": manifest_path,
        "manifest_error": manifest_error,
        "targets": {},
        "storage_backend": storage_cfg.get("BACKEND"),
    }
    ok = True

    for key in TARGET_KEYS:
        norm_key = key.lstrip("/")
        mapping = variants_index.get(norm_key) or {}
        print(f"\n- {key}")
        if not mapping:
            print("  (no variants found in manifest)")
            ok = False
        details: Dict[str, object] = {
            "manifest_entry": mapping,
            "variants": {},
        }
        for fmt, rel in mapping.items():
            info = _storage_path(str(rel))
            details["variants"][fmt] = info
            missing = not info.get("storage_exists") or not info.get("fs_exists")
            status = "ok" if not missing else "missing"
            print(
                f"  * {fmt}: {info['rel']} -> storage={info['storage_exists']} fs={info['fs_exists']} ({status})"
            )
            if missing:
                ok = False
        summary["targets"][key] = details

    summary["ok"] = ok
    return summary
