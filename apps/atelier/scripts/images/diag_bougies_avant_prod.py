"""Diagnostic ciblé sur les variantes bougies-avant en configuration prod."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Tuple

from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage

from apps.common.runscript_harness import binary_harness

TARGET_CANDIDATES: Tuple[str, ...] = (
    "images/components/wipe/bougies-avant.png",
    "images/components/wipe/bougies-avant.jpg",
    "images/components/wipe/bougies-avant.webp",
)

FORMATS: Tuple[str, ...] = ("avif", "webp", "png")


def _info_for_rel(rel: str) -> Dict[str, object]:
    rel_norm = rel.lstrip("/")
    info: Dict[str, object] = {"rel": rel_norm}

    try:
        exists = staticfiles_storage.exists(rel_norm)
    except Exception as exc:  # pragma: no cover - diagnostic helper
        exists = False
        info["storage_error"] = str(exc)
    info["storage_exists"] = exists

    try:
        fs_path = staticfiles_storage.path(rel_norm)
    except Exception as exc:  # pragma: no cover - remote storage
        info["fs_path"] = None
        info["fs_exists"] = None
        info["fs_error"] = str(exc)
    else:
        info["fs_path"] = fs_path
        info["fs_exists"] = Path(fs_path).exists()
    return info


def _variants_entry() -> Tuple[str, Dict[str, str]]:
    try:
        variants_index = getattr(staticfiles_storage, "variants_index", {}) or {}
    except Exception as exc:  # pragma: no cover - diagnostic helper
        print(f"[diag] ERREUR lecture variants_index: {exc}")
        variants_index = {}

    for candidate in TARGET_CANDIDATES:
        entry = variants_index.get(candidate)
        if entry:
            return candidate, entry
    return TARGET_CANDIDATES[0], variants_index.get(TARGET_CANDIDATES[0], {})


def _manifest_paths() -> Dict[str, str]:
    try:
        with staticfiles_storage.manifest_storage.open(staticfiles_storage.manifest_name) as fh:
            payload = json.load(fh)
    except Exception as exc:  # pragma: no cover - diagnostic helper
        print(f"[diag] ERREUR lecture manifest: {exc}")
        return {}
    paths = payload.get("paths") or {}
    if isinstance(paths, dict):
        return {str(k): str(v) for k, v in paths.items()}
    return {}


@binary_harness
def run() -> Dict[str, object]:  # pragma: no cover - diagnostic script
    print("=== diag bougies-avant (prod) ===")
    print(f"DJANGO_SETTINGS_MODULE={settings.SETTINGS_MODULE}")
    print(f"STATIC_URL={settings.STATIC_URL}")
    print(f"STATIC_ROOT={settings.STATIC_ROOT}")

    storage_cfg = getattr(settings, "STORAGES", {}).get("staticfiles", {})
    backend = storage_cfg.get("BACKEND")
    print(f"STATICFILES_STORAGE backend={backend}")
    print(f"storage class={staticfiles_storage.__class__.__module__}.{staticfiles_storage.__class__.__name__}")

    manifest_name = getattr(staticfiles_storage, "manifest_name", None)
    manifest_path = None
    manifest_error = None
    if manifest_name:
        try:
            manifest_path = staticfiles_storage.path(manifest_name)
        except Exception as exc:
            manifest_error = str(exc)
    print(f"manifest_name={manifest_name}")
    if manifest_path:
        print(f"manifest_path={manifest_path}")
    if manifest_error:
        print(f"manifest_path_error={manifest_error}")

    key_used, mapping = _variants_entry()
    print(f"\n[variants_index] key_used={key_used}")
    if not mapping:
        print("  aucune entrée _variants trouvée pour ce visuel")
    else:
        for fmt, rel in mapping.items():
            print(f"  - {fmt}: {rel}")

    details: Dict[str, object] = {
        "key_used": key_used,
        "variants_entry": mapping,
        "variants": {},
        "manifest_paths": {},
    }

    manifest_paths = _manifest_paths()

    for fmt in FORMATS:
        rel = mapping.get(fmt)
        if not rel:
            continue
        info = _info_for_rel(rel)
        details["variants"][fmt] = info
        manifest_rel = manifest_paths.get(rel.lstrip("/"))
        if manifest_rel:
            details["manifest_paths"][rel] = manifest_rel
        status = "OK"
        if not info.get("storage_exists") or not info.get("fs_exists"):
            status = "MISSING"
        print(
            f"[variant] {fmt}: rel={info['rel']} storage_exists={info['storage_exists']} "
            f"fs_path={info.get('fs_path')} fs_exists={info.get('fs_exists')} status={status}"
        )
        if manifest_rel:
            print(f"          manifest path entry -> {manifest_rel}")

    # Info about original hashed entry
    original_paths = {}
    for candidate in TARGET_CANDIDATES:
        manifest_value = manifest_paths.get(candidate)
        if manifest_value:
            original_paths[candidate] = manifest_value
    if original_paths:
        print("\n[manifest paths] originaux:")
        for k, v in original_paths.items():
            print(f"  {k} -> {v}")
    else:
        print("\n[manifest paths] originaux absents")

    details["manifest_originals"] = original_paths
    details["ok"] = True
    return details
