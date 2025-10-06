from rest_framework.throttling import SimpleRateThrottle
from .antispam import normalize_email

class LeadsIPThrottle(SimpleRateThrottle):
    scope = "leads_ip"
    def get_cache_key(self, request, view):
        ip = self.get_ident(request)
        kind = (request.data.get("form_kind") or "").strip()
        return f"leads:throttle:ip:{ip}:{kind}"

class LeadsEmailThrottle(SimpleRateThrottle):
    scope = "leads_email"
    def get_cache_key(self, request, view):
        email = normalize_email(request.data.get("email"))
        if not email:
            return None
        kind = (request.data.get("form_kind") or "").strip()
        return f"leads:throttle:email:{email}:{kind}"