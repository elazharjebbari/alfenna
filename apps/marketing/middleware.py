from django.conf import settings
from django.utils.deprecation import MiddlewareMixin


class SeoGuardMiddleware(MiddlewareMixin):
    """
    Ajoute X-Robots-Tag aux endpoints non indexables.
    Optionnel : 301 vers canonical si SEO_STRICT_CANONICAL=True (à implémenter si besoin).
    """
    BLOCK_PATH_PREFIXES = ("/api/", "/learning/stream/", "/billing/webhook/")

    def process_response(self, request, response):
        path = request.path
        preview = bool(request.GET.get("preview"))
        is_blocked = preview or any(path.startswith(p) for p in self.BLOCK_PATH_PREFIXES)
        if is_blocked:
            response["X-Robots-Tag"] = "noindex, nofollow"
        elif getattr(settings, "SEO_ENV", "dev") != "prod" and getattr(settings, "SEO_FORCE_NOINDEX_NONPROD", True):
            response["X-Robots-Tag"] = "noindex, nofollow"
        return response


class ConsentDebugHeadersMiddleware:
    """Expose des en-têtes X-Consent-* en prod uniquement si activé."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.enabled = getattr(settings, "CONSENT_DEBUG_HEADERS", False)

    def __call__(self, request):
        response = self.get_response(request)
        if not self.enabled:
            return response

        consent_name = getattr(settings, "CONSENT_COOKIE_NAME", "cookie_consent_marketing")
        try:
            consent_value = request.COOKIES.get(consent_name, "")
        except Exception:
            consent_value = ""

        response["X-Consent-Marketing-Name"] = consent_name
        response["X-Consent-Marketing-Value"] = str(consent_value)
        response["X-Analytics-Bootstrap"] = "expected:/static/site/analytics_bootstrap.js"
        return response
