"""Shared helpers for messaging components."""
from __future__ import annotations

from django.conf import settings


def secure_base_url() -> str:
    """Return the base URL used for signed links.

    In tests the fallback remains ``http://testserver`` so Django's client
    can resolve links without additional configuration. In non-debug
    environments we reject insecure HTTP values early to avoid leaking
    signed URLs over cleartext.
    """

    base = (getattr(settings, "MESSAGING_SECURE_BASE_URL", "") or "http://testserver").rstrip("/")
    if base.startswith("http://"):
        if not getattr(settings, "DEBUG", False):
            raise ValueError("MESSAGING_SECURE_BASE_URL must be HTTPS when DEBUG=False")
        return base
    return base or "http://testserver"
