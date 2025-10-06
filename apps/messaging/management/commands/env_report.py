from __future__ import annotations

import os
import re

from django.conf import settings
from django.core.management.base import BaseCommand

MASK = re.compile(r".")


def _mask(value: str) -> str:
    if not value:
        return "MISSING"
    if len(value) <= 4:
        return "***"
    return value[0] + "***" + value[-1]


KEYS = [
    "DJANGO_SETTINGS_MODULE",
    "DEFAULT_FROM_EMAIL",
    "EMAIL_BACKEND",
    "EMAIL_HOST",
    "EMAIL_PORT",
    "EMAIL_USE_SSL",
    "EMAIL_USE_TLS",
    "EMAIL_HOST_USER",
    "EMAIL_HOST_PASSWORD",
    "MESSAGING_SECURE_BASE_URL",
    "CELERY_BROKER_URL",
    "CELERY_RESULT_BACKEND",
    "DEV_EMAIL_CONSOLE",
    "EMAIL_PREFLIGHT_REQUIRED",
    "EMAIL_BACKEND_ENFORCE_SMTP",
    "EMAIL_PREFLIGHT_MODE",
    "EMAIL_PREFLIGHT_TO",
]


class Command(BaseCommand):
    help = "Affiche les variables d'environnement ET les settings e-mail, masquées."

    def handle(self, *args, **options) -> None:
        print("\n=== ENV REPORT (web process) ===\n")
        for key in KEYS:
            env_value = os.getenv(key)
            settings_value = getattr(settings, key, None)

            def fmt(raw_value):
                if raw_value is None:
                    return "∅"
                if "PASSWORD" in key or "EMAIL_HOST_USER" in key:
                    return _mask(str(raw_value))
                return repr(raw_value)

            print(
                f"• {key:<28} env={fmt(env_value)}  |  settings={fmt(settings_value)}"
            )
        print("\nNote: settings peuvent dériver d'autres variables (bools, int).")
