from __future__ import annotations

from django.conf import settings
from django.http import HttpResponsePermanentRedirect
from django.utils.deprecation import MiddlewareMixin


def _supported_languages() -> set[str]:
    configured = getattr(settings, "LANGUAGE_PREFIXES", None)
    if configured:
        return {code.lower() for code in configured}
    return {code for code, _ in getattr(settings, "LANGUAGES", ())}


class LanguagePrefixMiddleware(MiddlewareMixin):
    """
    Detect language prefixes in the URL, normalise the path, and persist the choice.

    Precedence: explicit prefix > cookie > Accept-Language (handled later).
    """

    cookie_name = getattr(settings, "LANGUAGE_COOKIE_NAME", "lang")
    cookie_max_age = getattr(settings, "LANGUAGE_COOKIE_MAX_AGE", 60 * 60 * 24 * 180)
    default_site_prefix = getattr(settings, "LANGUAGE_DEFAULT_SITE_PREFIX", "")

    def process_request(self, request):
        path = request.path_info or "/"
        if not path.startswith("/"):
            path = "/" + path

        segments = path.split("/")
        if len(segments) <= 1:
            return None

        candidate = (segments[1] or "").strip().lower()
        supported_languages = _supported_languages() or {"fr", "ar", "en"}
        if candidate not in supported_languages:
            return None

        remaining_segments = segments[2:]
        had_trailing_slash = path.endswith("/") and path != "/"
        new_path = "/" + "/".join(filter(None, remaining_segments))
        if new_path in {"", "//"}:
            new_path = "/"
        elif had_trailing_slash and not new_path.endswith("/"):
            new_path += "/"

        request.url_lang = candidate
        request.lang_from_path = candidate
        request.path_info = new_path
        try:
            request.path = new_path
        except Exception:
            pass

        # When visiting /fr/... without explicit site container, redirect to default container.
        site_version = getattr(request, "site_version", None)
        if site_version in (None, "", "core") and self.default_site_prefix:
            target = self._build_alias_target(candidate, remaining_segments)
            if target:
                return HttpResponsePermanentRedirect(target)

        return None

    def process_response(self, request, response):
        lang = getattr(request, "lang_from_path", None)
        if lang:
            response.set_cookie(
                self.cookie_name,
                lang,
                max_age=self.cookie_max_age,
                httponly=False,
                secure=getattr(settings, "SESSION_COOKIE_SECURE", False),
                samesite="Lax",
            )
        return response

    def _build_alias_target(self, lang: str, remaining_segments: list[str]) -> str | None:
        prefix = self.default_site_prefix.strip("/")
        if not prefix:
            return None

        tail = "/".join(filter(None, remaining_segments))
        if tail:
            return f"/{prefix}/{lang}/{tail}"
        return f"/{prefix}/{lang}"


__all__ = ["LanguagePrefixMiddleware"]
