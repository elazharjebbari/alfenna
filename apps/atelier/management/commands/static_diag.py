"""Dump key static files configuration entries for diagnostics."""
from __future__ import annotations

import os
from typing import List

from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.management.base import BaseCommand, CommandError

EXPECTED_STORAGE = "apps.atelier.staticbuild.storage.VariantManifestStaticFilesStorage"


class Command(BaseCommand):
    help = "Inspect staticfiles configuration and WhiteNoise wiring."

    def handle(self, *args, **options) -> None:  # pragma: no cover - diagnostic command
        env_settings = os.environ.get("DJANGO_SETTINGS_MODULE", "")
        self.stdout.write("=== static files diagnostics ===")
        self.stdout.write(f"DJANGO_SETTINGS_MODULE: {env_settings or '(unset)'}")
        self.stdout.write(f"DEBUG: {getattr(settings, 'DEBUG', '(unknown)')}")
        self.stdout.write(f"STATIC_URL: {getattr(settings, 'STATIC_URL', '(unset)')}")
        self.stdout.write(f"STATIC_ROOT: {getattr(settings, 'STATIC_ROOT', '(unset)')}")

        storage_backend = f"{staticfiles_storage.__class__.__module__}.{staticfiles_storage.__class__.__name__}"
        configured_backend = getattr(settings, "STORAGES", {}).get("staticfiles", {}).get("BACKEND")
        self.stdout.write(f"STATICFILES_STORAGE runtime: {storage_backend}")
        if configured_backend and configured_backend != storage_backend:
            self.stdout.write(f"STATICFILES_STORAGE configured: {configured_backend}")

        if storage_backend != EXPECTED_STORAGE:
            raise CommandError(
                f"Unexpected storage backend {storage_backend}; expected {EXPECTED_STORAGE}"
            )

        w_mw = "whitenoise.middleware.WhiteNoiseMiddleware"
        middleware: List[str] = list(getattr(settings, "MIDDLEWARE", []))
        if not middleware:
            raise CommandError("MIDDLEWARE setting is empty; WhiteNoise cannot be validated")

        try:
            idx = middleware.index(w_mw)
        except ValueError as exc:
            raise CommandError("WhiteNoiseMiddleware missing from MIDDLEWARE") from exc

        self.stdout.write(f"WhiteNoiseMiddleware position: index={idx}")

        security_mw = "django.middleware.security.SecurityMiddleware"
        if security_mw in middleware and middleware.index(security_mw) + 1 != idx:
            self.stdout.write(
                "WARNING: WhiteNoiseMiddleware should immediately follow SecurityMiddleware"
            )

        self.stdout.write(
            f"WHITENOISE_USE_FINDERS: {getattr(settings, 'WHITENOISE_USE_FINDERS', '(unset)')}"
        )
        self.stdout.write(
            f"WHITENOISE_AUTOREFRESH: {getattr(settings, 'WHITENOISE_AUTOREFRESH', '(unset)')}"
        )

        variants_len = len(getattr(staticfiles_storage, "variants_index", {}) or {})
        self.stdout.write(f"variants_index entries: {variants_len}")
        self.stdout.write("=== end diagnostics ===")
