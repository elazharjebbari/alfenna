"""Temporary compatibility wrapper for legacy imports.

The new billing service layer lives in ``apps.billing.services`` (package).
This module simply re-exports the public API so third-party code that still
imports ``apps.billing.services`` as a module keeps functioning.
"""

from .services import *  # noqa: F401,F403
