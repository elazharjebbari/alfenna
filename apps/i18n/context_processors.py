from __future__ import annotations

from django.conf import settings

DEFAULT_LANG = getattr(settings, "LANGUAGE_CODE", "fr")
RTL_LANGUAGES = {code.split("-")[0] for code in getattr(settings, "RTL_LANGUAGES", {"ar"})}


def language_direction(request):
    segments = getattr(request, "_segments", None)
    lang = getattr(segments, "lang", None) or getattr(request, "LANGUAGE_CODE", DEFAULT_LANG)
    lang = (lang or DEFAULT_LANG).lower()
    primary = lang.split("-")[0]
    is_rtl = primary in RTL_LANGUAGES
    return {
        "lang_code": lang,
        "lang_dir": "rtl" if is_rtl else "ltr",
        "is_rtl": is_rtl,
    }


__all__ = ["language_direction"]
