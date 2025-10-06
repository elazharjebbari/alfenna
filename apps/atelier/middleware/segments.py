# apps/atelier/middleware/segments.py
from dataclasses import dataclass

from apps.marketing.helpers import has_marketing_consent

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
        # Langue (header -> 'fr'/'en')
        lang_hdr = (request.headers.get("Accept-Language") or "fr")
        lang = lang_hdr.split(",")[0].split("-")[0].lower() or "fr"

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

        request._segments = Segments(
            lang=lang, device=device, consent=consent,
            source=source, campaign=campaign, qa=qa
        )
        return self.get_response(request)
