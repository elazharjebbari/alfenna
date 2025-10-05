# apps/marketing/signals.py
from __future__ import annotations
import logging
from django.core.management import call_command
from django.db.models.signals import post_migrate
from django.dispatch import receiver


logger = logging.getLogger("pricing.seed")

@receiver(post_migrate)
def ensure_marketing_config(sender, **kwargs):
    # Ne fait quelque chose que lorsque l'app 'marketing' a migré
    if getattr(sender, "label", "") != "marketing":
        return
    try:
        from apps.marketing.models.models_base import MarketingConfig
        if not MarketingConfig.objects.exists():
            MarketingConfig.objects.create(site_name="Site")
    except Exception:
        # silencieux si migrations pas prêtes
        pass


@receiver(post_migrate)
def ensure_price_plans(sender, **kwargs):
    if getattr(sender, "label", "") != "marketing":
        return

    try:
        from apps.marketing.models.models_pricing import PricePlan
    except Exception as exc:  # pragma: no cover - import errors during migrations
        logger.warning("Pricing fixtures skipped: %s", exc)
        return

    expected_slugs = {"starter", "createur"}
    existing = set(PricePlan.objects.filter(slug__in=expected_slugs).values_list("slug", flat=True))

    if expected_slugs.issubset(existing):
        logger.info("Pricing fixtures already present")
        return

    missing = sorted(expected_slugs - existing)
    try:
        call_command("loaddata", "lumierelearning/fixtures/price_plans.json", verbosity=0)
        logger.info("Loaded pricing fixtures for: %s", ", ".join(missing) if missing else "starter, createur")
    except Exception as exc:
        logger.warning("Failed to load pricing fixtures: %s", exc)
