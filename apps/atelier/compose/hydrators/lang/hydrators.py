from __future__ import annotations

from typing import Any, Dict, List

from django.http import HttpRequest
from django.urls import resolve
from django.utils.translation import get_language


def _build_lang_url(request: HttpRequest, code: str) -> str:
    path = request.path
    if path.startswith("/maroc/"):
        base = "/maroc"
        rest = path[len(base):]
    else:
        base = ""
        rest = path

    segments = [seg for seg in rest.split("/") if seg]
    if segments and segments[0] in {"fr", "ar"}:
        segments = segments[1:]

    new_path = "/".join([base.strip("/"), code] + segments)
    new_path = "/" + new_path.strip("/")
    if request.META.get("QUERY_STRING"):
        new_path += f"?{request.META['QUERY_STRING']}"
    return new_path


def language_switcher(request: HttpRequest, params: Dict[str, Any]) -> Dict[str, Any]:
    locales = params.get("locales") or []
    if not isinstance(locales, list):
        locales = []

    current_lang = getattr(request, "LANGUAGE_CODE", None) or get_language() or "fr"
    current_lang = current_lang.lower().split("-")[0]

    options: List[Dict[str, Any]] = []
    for entry in locales:
        if not isinstance(entry, dict):
            continue
        code = str(entry.get("code") or "").strip().lower()
        if not code:
            continue
        label = entry.get("label") or code.upper()
        url = entry.get("url")
        if not url:
            url = _build_lang_url(request, code)
        options.append({
            "code": code,
            "label": label,
            "url": url,
            "is_active": code == current_lang,
            "rtl": bool(entry.get("rtl"))
        })

    breakpoint = params.get("breakpoint") or "lg"

    return {
        "options": options,
        "breakpoint": breakpoint,
    }
