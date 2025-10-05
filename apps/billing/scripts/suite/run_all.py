"""Compatibility wrapper for legacy entry point."""
from __future__ import annotations

from apps.billing.scripts.run_all import run as new_run


def run(*args, **kwargs):
    return new_run(*args, **kwargs)
