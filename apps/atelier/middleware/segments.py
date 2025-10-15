# apps/atelier/middleware/segments.py
from dataclasses import dataclass

from django.conf import settings
from apps.marketing.helpers import has_marketing_consent
from django.utils import translation

@dataclass
class Segments:
    lang: str = "fr"
    device: str = "d"   # d=desktop, m=mobile
    consent: str = "N"  # Y|N
    source: str = ""
    campaign: str = ""
    qa: bool = False

class SegmentResolverMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        existing_segments = getattr(request, "_segments", None)
        if existing_segments and getattr(existing_segments, "lang", None):
            lang = existing_segments.lang
        else:
            url_lang = (getattr(request, "url_lang", "") or "").strip().lower()
            if url_lang:
                lang = url_lang
            else:
                cookie_lang = (request.COOKIES.get(getattr(settings, "LANGUAGE_COOKIE_NAME", "lang"), "") or "").strip().lower()
                if cookie_lang:
                    lang = cookie_lang
                else:
                    lang_hdr = (request.headers.get("Accept-Language") or "fr")
                    lang = lang_hdr.split(",")[0].split("-")[0].lower() or "fr"
        if not lang:
            lang = "fr"
        request.META.setdefault("HTTP_ACCEPT_LANGUAGE", lang)
        translation.activate(lang)
        request.LANGUAGE_CODE = lang

        # Device (UA simple)
        ua = (request.META.get("HTTP_USER_AGENT", "") or "").lower()
        device = "m" if any(k in ua for k in ["iphone", "android", "mobile"]) else "d"

        # Consent (aligné aux settings)
        consent = "Y" if has_marketing_consent(request) else "N"

        # Source / campagne (utm)
        source = request.GET.get("utm_source", "") or ""
        campaign = request.GET.get("utm_campaign", "") or ""

        # QA flag (piloté ailleurs par preview; ici reste False)
        qa = False

        segments = Segments(
            lang=lang, device=device, consent=consent,
            source=source, campaign=campaign, qa=qa
        )
        request._segments = segments
        return self.get_response(request)
