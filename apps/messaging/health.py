"""Health and preflight checks for outbound e-mail infrastructure."""
from __future__ import annotations

from contextlib import suppress

from typing import Any

from django.conf import settings
from django.core.mail import EmailMessage, get_connection


def ensure_email_ready(*, raise_on_fail: bool = True) -> bool:
    """Validate that the configured e-mail backend is ready for production use.

    When ``raise_on_fail`` is true (default), any failure raises ``RuntimeError`` so the
    caller can abort startup. When false the function returns ``False`` on failure.
    """

    def fail(message: str) -> bool:
        if raise_on_fail:
            raise RuntimeError(f"[EMAIL PREFLIGHT] {message}")
        return False

    backend_name = getattr(settings, "EMAIL_BACKEND", "") or ""
    if getattr(settings, "EMAIL_BACKEND_ENFORCE_SMTP", False) and "smtp" not in backend_name.lower():
        return fail(f"EMAIL_BACKEND='{backend_name}' doit être un backend SMTP")

    connection: Any | None = None
    try:
        connection = get_connection()
        timeout = getattr(settings, "EMAIL_PREFLIGHT_TIMEOUT", 8)
        if hasattr(connection, "timeout") and not getattr(connection, "timeout", None):
            connection.timeout = timeout  # type: ignore[attr-defined]
        connection.open()
    except Exception as exc:  # pragma: no cover - exercised in tests via fail path
        return fail(f"Échec de connexion SMTP: {exc}")

    try:
        mode = getattr(settings, "EMAIL_PREFLIGHT_MODE", "connect")
        if mode == "send":
            recipient = (
                getattr(settings, "EMAIL_PREFLIGHT_TO", "")
                or getattr(settings, "EMAIL_HOST_USER", "")
            ).strip()
            if not recipient:
                return fail("EMAIL_PREFLIGHT_TO doit être défini lorsque EMAIL_PREFLIGHT_MODE=send")
            try:
                EmailMessage(
                    subject="[preflight] OK",
                    body="Email preflight successful.",
                    from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None) or "no-reply@localhost",
                    to=[recipient],
                ).send(fail_silently=False)
            except Exception as exc:  # pragma: no cover - covered via tests raising
                return fail(f"Échec d'envoi d'e-mail de test: {exc}")
    finally:
        if connection is not None:
            with suppress(Exception):
                connection.close()

    return True


__all__ = ["ensure_email_ready"]
