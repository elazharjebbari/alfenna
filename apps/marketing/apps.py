from django.apps import AppConfig


class MarketingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.marketing"
    label = "marketing"
    verbose_name = "Marketing & SEO"

    def ready(self):
        from . import signals
