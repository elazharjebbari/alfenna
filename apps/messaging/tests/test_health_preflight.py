from __future__ import annotations

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "alfenna.settings.test_cli")

import django

django.setup()

from django.test import SimpleTestCase, override_settings

from apps.messaging.health import ensure_email_ready


class EnsureEmailReadyTests(SimpleTestCase):
    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_BACKEND_ENFORCE_SMTP=False,
        EMAIL_PREFLIGHT_MODE="connect",
        DEFAULT_FROM_EMAIL="noreply@example.com",
    )
    def test_connect_mode_locmem_backend(self) -> None:
        self.assertTrue(ensure_email_ready(raise_on_fail=True))

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
        EMAIL_BACKEND_ENFORCE_SMTP=True,
        DEFAULT_FROM_EMAIL="noreply@example.com",
    )
    def test_enforce_smtp_rejects_non_smtp_backend(self) -> None:
        self.assertFalse(ensure_email_ready(raise_on_fail=False))

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_BACKEND_ENFORCE_SMTP=False,
        EMAIL_PREFLIGHT_MODE="send",
        EMAIL_PREFLIGHT_TO="",
        EMAIL_HOST_USER="",
        DEFAULT_FROM_EMAIL="noreply@example.com",
    )
    def test_send_mode_requires_recipient(self) -> None:
        self.assertFalse(ensure_email_ready(raise_on_fail=False))

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_BACKEND_ENFORCE_SMTP=False,
        EMAIL_PREFLIGHT_MODE="send",
        EMAIL_PREFLIGHT_TO="ops@example.com",
        DEFAULT_FROM_EMAIL="noreply@example.com",
    )
    def test_send_mode_succeeds_with_recipient(self) -> None:
        self.assertTrue(ensure_email_ready(raise_on_fail=True))
