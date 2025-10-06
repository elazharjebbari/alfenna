"""Run the full billing script suite (smoke + diagnostics)."""
from __future__ import annotations

import importlib
from typing import Iterable

from django.conf import settings

from apps.billing.services import PaymentService
from apps.common.runscript_harness import binary_harness

SCRIPT_MODULES: Iterable[str] = (
    "apps.billing.scripts.smoke",
    "apps.billing.scripts.crawler",
    "apps.billing.scripts.checkout_plan_smoke",
    "apps.billing.scripts.checkout_assets_probe",
    "apps.billing.scripts.checkout_intent_probe",
    "apps.billing.scripts.e2e_purchase_and_invoice",
    "apps.billing.scripts.e2e_refund_and_email",
)

def _prepare_environment() -> None:
    """Ensure scripts run in Stripe offline mode and fresh order service."""

    settings.STRIPE_SECRET_KEY = ""
    settings.STRIPE_WEBHOOK_SECRET = ""
    PaymentService._orders = None  # reset cached order service


def _execute(module_path: str) -> tuple[bool, list[str]]:
    module = importlib.import_module(module_path)
    run_fn = getattr(module, "run", None)
    if run_fn is None:
        return False, [f"{module_path} has no run() function"]
    inner = getattr(run_fn, "__wrapped__", run_fn)
    result = inner()
    if isinstance(result, dict):
        return bool(result.get("ok", False)), list(result.get("logs", []))
    return bool(result), []


@binary_harness
def run(*_args, **_kwargs):
    _prepare_environment()
    aggregate_logs: list[str] = []
    failures: list[str] = []
    for module_path in SCRIPT_MODULES:
        ok, logs = _execute(module_path)
        aggregate_logs.append(f"{module_path}: {'OK' if ok else 'KO'}")
        aggregate_logs.extend(logs)
        if not ok:
            failures.append(module_path)
    if failures:
        aggregate_logs.append(f"Failures: {', '.join(failures)}")
        return {"ok": False, "name": "billing_run_all", "duration": 0.0, "logs": aggregate_logs}
    aggregate_logs.append("All billing scripts completed successfully")
    return {"ok": True, "name": "billing_run_all", "duration": 0.0, "logs": aggregate_logs}
