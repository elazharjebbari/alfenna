"""Throttle classes for analytics endpoints."""
from rest_framework.throttling import SimpleRateThrottle


class AnalyticsIPThrottle(SimpleRateThrottle):
    scope = "analytics_collect"
    rate = "120/min"

    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        if not ident:
            return None
        return self.cache_format % {"scope": self.scope, "ident": ident}


__all__ = ["AnalyticsIPThrottle"]
