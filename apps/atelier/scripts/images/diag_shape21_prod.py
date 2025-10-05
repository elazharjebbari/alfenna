"""Diagnostics for shape-21 variants under prod settings."""
from __future__ import annotations

from pathlib import Path
from typing import Dict

from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage

from apps.common.runscript_harness import binary_harness

TARGET_REL = "images/shape/shape-21.png"
KNOWN_REL = "images/shape/shape-21.830790d4c146/shape-21.830790d4c146.d63c7713da4e.avif"
FORMATS = ("avif", "webp", "png", "jpg")


def _info_for(rel: str) -> Dict[str, object]:
    rel_norm = rel.lstrip("/")
    info: Dict[str, object] = {"rel": rel_norm}
    try:
        info["storage_exists"] = staticfiles_storage.exists(rel_norm)
    except Exception as exc:  # pragma: no cover - diagnostic helper
        info["storage_exists"] = False
        info["storage_error"] = str(exc)

    try:
        fs_path = staticfiles_storage.path(rel_norm)
        info["fs_path"] = fs_path
        info["fs_exists"] = Path(fs_path).exists()
    except Exception as exc:  # pragma: no cover - remote storage
        info["fs_error"] = str(exc)
        info["fs_path"] = None
        info["fs_exists"] = None
    return info


@binary_harness
def run() -> Dict[str, object]:  # pragma: no cover - diagnostic script
    print("=== shape-21 prod variant diagnostics ===")
    print(f"DJANGO_SETTINGS_MODULE={settings.SETTINGS_MODULE}")
    print(f"STATIC_URL={settings.STATIC_URL}")
    print(f"STATIC_ROOT={settings.STATIC_ROOT}")
    storage_cfg = getattr(settings, "STORAGES", {}).get("staticfiles", {})
    print(f"STATICFILES_STORAGE={storage_cfg.get('BACKEND')}")

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

    manifest_entry = None
    for candidate in (TARGET_REL, TARGET_REL.replace(".png", ".jpg"), TARGET_REL.replace(".png", ".webp")):
        manifest_entry = variants_index.get(candidate)
        if manifest_entry:
            print(f"Manifest key used: {candidate}")
            break
    else:
        candidate = TARGET_REL
        print("Manifest entry not found for any candidate key")

    summary: Dict[str, object] = {
        "target_original": candidate,
        "manifest_entry": manifest_entry or {},
        "variants": {},
        "known_url": _info_for(KNOWN_REL),
        "storage_backend": storage_cfg.get("BACKEND"),
    }

    ok = True

    if manifest_entry:
        for fmt in FORMATS:
            rel = manifest_entry.get(fmt)
            if not rel:
                continue
            info = _info_for(rel)
            summary["variants"][fmt] = info
            missing = not info.get("storage_exists") or not info.get("fs_exists")
            status = "OK" if not missing else "MISSING"
            print(f"  {fmt.upper():4} → {info['rel']} :: storage={info.get('storage_exists')} fs={info.get('fs_exists')} [{status}]")
            if missing:
                ok = False
    else:
        ok = False

    target_info = summary["known_url"]
    print("Known URL rel=", target_info["rel"])
    print("  storage_exists=", target_info.get("storage_exists"))
    print("  fs_path=", target_info.get("fs_path"))
    print("  fs_exists=", target_info.get("fs_exists"))
    if not target_info.get("storage_exists") or not target_info.get("fs_exists"):
        ok = False

    summary["ok"] = ok
    return summary
