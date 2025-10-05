from __future__ import annotations

import os
import smtplib
import ssl
from dataclasses import dataclass
from typing import Iterable

from django.conf import settings

ICON = {"ok": "✅", "err": "❌", "warn": "⚠️", "info": "ℹ️"}
DEFAULT_TIMEOUT = int(os.getenv("SMTP_PROBE_TIMEOUT", "10"))


@dataclass(frozen=True)
class Probe:
    label: str
    host: str
    port: int
    use_ssl: bool
    use_tls: bool

    def describe(self) -> str:
        mode = "SSL" if self.use_ssl else ("STARTTLS" if self.use_tls else "PLAIN")
        return f"{self.host}:{self.port} [{mode}]"


def iter_probe_matrix() -> Iterable[Probe]:
    current_host = getattr(settings, "EMAIL_HOST", None) or os.getenv("EMAIL_HOST")
    current_port = getattr(settings, "EMAIL_PORT", None) or os.getenv("EMAIL_PORT")
    use_ssl = getattr(settings, "EMAIL_USE_SSL", None)
    use_tls = getattr(settings, "EMAIL_USE_TLS", None)

    if current_host and current_port:
        yield Probe(
            label="Configured",
            host=str(current_host),
            port=int(current_port),
            use_ssl=_coerce_flag(use_ssl),
            use_tls=_coerce_flag(use_tls),
        )

    yield from [
        Probe("Titan SSL", host="smtp.titan.email", port=465, use_ssl=True, use_tls=False),
        Probe("Titan STARTTLS", host="smtp.titan.email", port=587, use_ssl=False, use_tls=True),
        Probe("Gmail SSL", host="smtp.gmail.com", port=465, use_ssl=True, use_tls=False),
        Probe("Gmail STARTTLS", host="smtp.gmail.com", port=587, use_ssl=False, use_tls=True),
    ]


def _connect(probe: Probe, username: str, password: str) -> tuple[bool, str]:
    context = ssl.create_default_context()
    try:
        if probe.use_ssl:
            server = smtplib.SMTP_SSL(
                probe.host,
                probe.port,
                timeout=DEFAULT_TIMEOUT,
                context=context,
            )
        else:
            server = smtplib.SMTP(probe.host, probe.port, timeout=DEFAULT_TIMEOUT)
        with server:
            server.ehlo()
            if probe.use_tls:
                server.starttls(context=context)
                server.ehlo()
            if username and password:
                server.login(username, password)
        return True, "Login OK" if username and password else "Connect OK"
    except Exception as exc:  # pragma: no cover - interactive helper
        return False, repr(exc)


def _coerce_flag(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return False


def run(*args):  # pragma: no cover - debug helper
    username = os.getenv("EMAIL_HOST_USER", "")
    password = os.getenv("EMAIL_HOST_PASSWORD", "")

    print("\n=== SMTP PROBE MATRIX ===\n")
    if not username or not password:
        print(
            f"{ICON['warn']}  Credentials incomplets — login sera omis (EMAIL_HOST_USER / EMAIL_HOST_PASSWORD)."
        )
    else:
        print(f"{ICON['info']}  Tentative de login avec l'utilisateur configuré (masqué).")
    print()

    seen = set()
    for probe in iter_probe_matrix():
        if (probe.host, probe.port, probe.use_ssl, probe.use_tls) in seen:
            continue
        seen.add((probe.host, probe.port, probe.use_ssl, probe.use_tls))

        ok, message = _connect(probe, username, password)
        icon = ICON["ok" if ok else "err"]
        credential_note = " (sans login)" if not username or not password else ""
        print(f"{icon}  {probe.label:<15} → {probe.describe()} — {message}{credential_note}")

    print("\nCouper le worker avant d'ajuster les variables. Voir README pour guidance.")
