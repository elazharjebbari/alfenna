import time

from apps.atelier.compose.hydrators.pricing.hydrators import pricing_packs
from apps.common.runscript_harness import binary_harness


NAME = "pricing/packs hydrator"


@binary_harness
def run():
    started = time.time()
    logs, ok = [], True

    ctx = pricing_packs(None, {"fallback_plans": []})
    plans = ctx.get("plans") or []

    logs.append(f"Plans renvoyes: {len(plans)}")
    for plan in plans:
        logs.append(f"- {plan.get('slug', '?')} -> {plan.get('cta', {}).get('url', '')}")

    if not plans:
        ok = False

    duration = round(time.time() - started, 2)
    return {"ok": ok, "name": NAME, "duration": duration, "logs": logs}
