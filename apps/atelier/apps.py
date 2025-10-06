# apps/atelier/apps.py (montrer uniquement l’ajout)
from django.apps import AppConfig
import logging

log = logging.getLogger("apps.atelier.apps")

class AtelierConfig(AppConfig):
    name = "apps.atelier"
    verbose_name = "Atelier"

    def ready(self):
        log.info("AtelierConfig ready: skeleton loaded.")
        # === Autodiscovery des composants ===
        from .components import discovery
        from django.conf import settings

        # Découverte au boot (override=False par défaut)
        count, warns = discovery.discover(override_existing=True)
        if count:
            log.info("Atelier components discovered: %d", count)
        for w in warns:
            log.warning(w)

        # En dev: active l’autoreload sur manifests
        discovery.enable_dev_autoreload()
