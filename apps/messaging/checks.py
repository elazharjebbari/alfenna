"""Django system checks guarding e-mail configuration."""
from __future__ import annotations

from django.conf import settings
from django.core.checks import Error, Tags, register

from .health import ensure_email_ready


@register(Tags.compatibility)
def email_config_checks(app_configs=None, **kwargs):  # noqa: D401 - Django signature
    errors: list[Error] = []

    default_from = getattr(settings, "DEFAULT_FROM_EMAIL", "")
    if not default_from:
        errors.append(Error("DEFAULT_FROM_EMAIL doit être défini", id="email.E001"))

    backend_name = (getattr(settings, "EMAIL_BACKEND", "") or "").lower()
    if getattr(settings, "EMAIL_BACKEND_ENFORCE_SMTP", False) and "smtp" not in backend_name:
        errors.append(Error("EMAIL_BACKEND doit être de type SMTP en production", id="email.E002"))

    secure_base = getattr(settings, "MESSAGING_SECURE_BASE_URL", "") or ""
    if not getattr(settings, "DEBUG", False) and not secure_base.startswith("https://"):
        errors.append(Error("MESSAGING_SECURE_BASE_URL doit commencer par https://", id="email.E003"))

    if getattr(settings, "EMAIL_PREFLIGHT_REQUIRED", False):
        try:
            ensure_email_ready(raise_on_fail=True)
        except Exception as exc:  # pragma: no cover - exercised via tests producing error
            errors.append(Error(f"Pré-flight e-mail échoué: {exc}", id="email.E004"))

    return errors


__all__ = ["email_config_checks"]
