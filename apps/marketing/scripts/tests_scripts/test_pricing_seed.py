import time

from django.core.management import call_command

from apps.common.runscript_harness import binary_harness
from apps.marketing.models.models_pricing import PricePlan


NAME = "marketing.pricing_seed"
EXPECTED_SLUGS = {"starter", "createur"}


@binary_harness
def run():
    started = time.time()
    logs, ok = [], True

    existing = set(PricePlan.objects.filter(slug__in=EXPECTED_SLUGS).values_list("slug", flat=True))
    missing = sorted(EXPECTED_SLUGS - existing)

    if missing:
        call_command("loaddata", "alfenna/fixtures/price_plans.json", verbosity=0)
        logs.append("Fixtures price_plans.json chargees")
        existing = set(PricePlan.objects.filter(slug__in=EXPECTED_SLUGS).values_list("slug", flat=True))
        missing = sorted(EXPECTED_SLUGS - existing)

    for slug in sorted(EXPECTED_SLUGS):
        present = slug in existing
        logs.append(f"Plan {slug} present: {present}")
        if not present:
            ok = False

    details = PricePlan.objects.filter(slug__in=EXPECTED_SLUGS).values("slug", "price_cents", "currency")
    for row in details:
        logs.append(f"{row['slug']} -> {row['price_cents']} {row['currency']}")

    duration = round(time.time() - started, 2)
    return {"ok": ok and not missing, "name": NAME, "duration": duration, "logs": logs}
