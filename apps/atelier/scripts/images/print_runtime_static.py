"""Print runtime static configuration and resolve a specific relative path."""
from __future__ import annotations

from pathlib import Path
from typing import Dict

from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage
from django.http import HttpResponse
from django.urls import path

TARGET_PARAM = "rel"
DEFAULT_REL = "images/shape/shape-21.830790d4c146/shape-21.830790d4c146.d63c7713da4e.avif"


def _info(rel: str) -> Dict[str, object]:
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
    except Exception as exc:  # pragma: no cover - diagnostic helper
        info["fs_path"] = None
        info["fs_exists"] = None
        info["fs_error"] = str(exc)
    return info


def runtime_view(request):  # pragma: no cover - runtime helper
    rel = request.GET.get(TARGET_PARAM, DEFAULT_REL)
    payload = {
        "DJANGO_SETTINGS_MODULE": settings.SETTINGS_MODULE,
        "STATIC_URL": settings.STATIC_URL,
        "STATIC_ROOT": settings.STATIC_ROOT,
        "STATICFILES_STORAGE": settings.STORAGES.get("staticfiles", {}).get("BACKEND"),
        "manifest_name": getattr(staticfiles_storage, "manifest_name", None),
        "manifest_path": None,
        "target": _info(rel),
    }
    manifest_name = payload["manifest_name"]
    if manifest_name:
        try:
            payload["manifest_path"] = staticfiles_storage.path(manifest_name)
        except Exception as exc:
            payload["manifest_path_error"] = str(exc)

    lines = ["Runtime static debug:"]
    for key, value in payload.items():
        lines.append(f"- {key}: {value}")
    return HttpResponse("\n".join(lines), content_type="text/plain")


urlpatterns = [
    path("__static_debug__", runtime_view),
]
