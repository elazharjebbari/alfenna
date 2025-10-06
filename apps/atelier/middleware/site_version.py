from __future__ import annotations

from django.utils.deprecation import MiddlewareMixin


class PathPrefixSiteVersionMiddleware(MiddlewareMixin):
    """Map URL prefixes to site version slugs and rewrite request.path_info."""

    def __init__(self, get_response=None):
        super().__init__(get_response)
        # Longest prefixes first to avoid partial matches.
        self.prefix_map = {
            "/maroc": "ma",
            "/france": "fr",
            # "/england": "en",  # futur
        }
        self.default_version = "core"

    def process_request(self, request):
        path: str = request.path_info or "/"
        for prefix, slug in self.prefix_map.items():
            if path == prefix or path.startswith(prefix + "/"):
                # Strip the prefix for internal routing and preserve leading slash.
                new_path = path[len(prefix):] or "/"
                if not new_path.startswith("/"):
                    new_path = "/" + new_path
                request.path_info = new_path
                request.site_version = slug
                break
        else:
            request.site_version = self.default_version
