from __future__ import annotations

from django.apps import AppConfig


class AdsBridgeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.adsbridge"
    verbose_name = "Google Ads Bridge"

    def ready(self) -> None:
        # Keep ready hook light; import signals when we have some.
        return None
