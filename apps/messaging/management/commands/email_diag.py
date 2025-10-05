from django.core.management.base import BaseCommand, CommandError

from apps.messaging.health import ensure_email_ready


class Command(BaseCommand):
    help = (
        "Vérifie la configuration e-mail: connexion SMTP obligatoire et, si demandé, "
        "envoi d'un e-mail de test."
    )

    def handle(self, *args, **options):
        try:
            ensure_email_ready(raise_on_fail=True)
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS("Email preflight OK"))
