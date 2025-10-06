from __future__ import annotations

import os
from unittest import mock

from django.conf import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "alfenna.settings.test_cli")

import django

django.setup()

from django.test import SimpleTestCase, override_settings

from apps.messaging.checks import email_config_checks


class EmailConfigChecksTests(SimpleTestCase):
    @override_settings(
        DEFAULT_FROM_EMAIL="",
        EMAIL_BACKEND_ENFORCE_SMTP=False,
        DEBUG=True,
    )
    def test_missing_default_from_email(self) -> None:
        errors = email_config_checks()
        ids = {error.id for error in errors}
        self.assertIn("email.E001", ids)

    @override_settings(
        DEFAULT_FROM_EMAIL="ops@example.com",
        EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
        EMAIL_BACKEND_ENFORCE_SMTP=True,
        DEBUG=True,
    )
    def test_non_smtp_backend_in_enforced_mode(self) -> None:
        errors = email_config_checks()
        ids = {error.id for error in errors}
        self.assertIn("email.E002", ids)

    @override_settings(
        DEFAULT_FROM_EMAIL="ops@example.com",
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_BACKEND_ENFORCE_SMTP=True,
        DEBUG=False,
        MESSAGING_SECURE_BASE_URL="http://insecure.example.com",
    )
    def test_insecure_base_url_in_prod(self) -> None:
        errors = email_config_checks()
        ids = {error.id for error in errors}
        self.assertIn("email.E003", ids)

    @override_settings(
        DEFAULT_FROM_EMAIL="ops@example.com",
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_BACKEND_ENFORCE_SMTP=True,
        EMAIL_PREFLIGHT_REQUIRED=True,
        DEBUG=False,
    )
    def test_preflight_failure_reported(self) -> None:
        with mock.patch("apps.messaging.checks.ensure_email_ready", side_effect=RuntimeError("boom")):
            errors = email_config_checks()
        ids = {error.id for error in errors}
        self.assertIn("email.E004", ids)
