from django.apps import AppConfig
import logging

log = logging.getLogger(__name__)

class FlowFormsConfig(AppConfig):
    name = "apps.flowforms"
    label = "flowforms"
    verbose_name = "Flow Forms"

    def ready(self):
        # Enregistrer les system checks
        from . import checks  # noqa: F401
        log.info("FlowForms loaded")