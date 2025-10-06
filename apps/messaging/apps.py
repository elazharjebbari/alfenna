from django.apps import AppConfig


class MessagingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.messaging"
    verbose_name = "Messaging"

    def ready(self) -> None:
        # Import system checks at startup.
        from . import checks  # noqa: F401
        import apps.messaging.tasks_debug  # noqa: F401
