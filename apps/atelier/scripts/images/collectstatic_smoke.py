"""Run collectstatic and report manifest statistics."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from django.conf import settings
from django.core.management import call_command

from apps.common.runscript_harness import binary_harness


@binary_harness
def run() -> Dict[str, object]:  # pragma: no cover - diagnostic script
    print("[collectstatic_smoke] collectstatic --noinput --clear")
    call_command("collectstatic", "--noinput", "--clear")

    manifest_path = Path(settings.STATIC_ROOT or "") / "staticfiles.json"
    if not manifest_path.exists():
        print(f"[collectstatic_smoke] ERROR manifest missing at {manifest_path}")
        return {"ok": False, "reason": "manifest missing", "manifest": str(manifest_path)}

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    variants = data.get("_variants") or {}
    paths = data.get("paths") or {}

    print(
        f"[collectstatic_smoke] manifest entries: variants={len(variants)} paths={len(paths)}"
    )

    return {
        "ok": True,
        "manifest": str(manifest_path),
        "variants": len(variants),
        "paths": len(paths),
    }
