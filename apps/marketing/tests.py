from __future__ import annotations

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.test import Client, RequestFactory, TestCase, override_settings

from apps.atelier.compose import pipeline
from apps.atelier.compose.hydrators.pricing.hydrators import pricing_packs
from apps.marketing.models.models_pricing import PricePlan, BonusFeature
from apps.marketing.signals import ensure_price_plans
from apps.marketing.context_processors import seo
from apps.marketing.helpers import CFG_CACHE_KEY
from apps.marketing.models.models_base import MarketingGlobal
from apps.marketing.middleware import ConsentDebugHeadersMiddleware


class PricePlanSeedingTests(TestCase):
    def _seed(self) -> None:
        sender = type("Sender", (), {"label": "marketing"})
        ensure_price_plans(sender=sender)

    def test_post_migrate_seeds_two_price_plans(self) -> None:
        PricePlan.objects.all().delete()

        self._seed()

        slugs = list(PricePlan.objects.order_by("slug").values_list("slug", flat=True))
        self.assertEqual(slugs, ["createur", "starter"])

        self._seed()
        self.assertEqual(PricePlan.objects.count(), 2)


class PricingHydratorTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.params = {
            "fallback_plans": [
                {"slug": "fallback", "title": "Fallback", "price_cents": 9900, "currency": "€"}
            ],
            "cta_default": {
                "label": "Je me lance",
                "url": "#cta",
                "aria": "Je me lance",
                "sublabel": "Paiement sécurisé",
            },
        }

    def test_hydrator_prefers_database_plans(self) -> None:
        PricePlan.objects.all().delete()
        PricePlan.objects.create(
            slug="starter",
            title="Starter DB",
            price_cents=2900,
            currency="€",
            features=["Feature DB"],
            priority=5,
            is_active=True,
        )
        PricePlan.objects.create(
            slug="createur",
            title="Createur DB",
            price_cents=27900,
            old_price_cents=33900,
            currency="€",
            value_breakdown=[{"label": "Bonus", "amount_cents": 5000}],
            priority=10,
            is_featured=True,
        )

        ctx = pricing_packs(None, self.params)
        slugs = [plan["slug"] for plan in ctx["plans"]]
        self.assertEqual(slugs, ["starter", "createur"])
        starter = ctx["plans"][0]
        self.assertEqual(starter["cta"]["url"], "/billing/checkout/plan/starter/")
        self.assertIn("Feature DB", starter["features"])
        self.assertFalse(starter.get("old_price_amount"))

    def test_hydrator_uses_fallback_when_db_empty(self) -> None:
        PricePlan.objects.all().delete()

        ctx = pricing_packs(None, self.params)

        self.assertEqual(len(ctx["plans"]), 1)
        self.assertEqual(ctx["plans"][0]["slug"], "fallback")
        self.assertEqual(ctx["plans"][0]["cta"]["url"], "/billing/checkout/plan/fallback/")

    def test_bonus_features_visible_for_target_plan(self) -> None:
        PricePlan.objects.all().delete()
        starter = PricePlan.objects.create(
            slug="starter",
            title="Starter",
            price_cents=1900,
            currency="€",
            features=["Bonus Starter"],
            priority=1,
            is_active=True,
        )
        BonusFeature.objects.create(plan=starter, label="Atelier live", icon_class="fa-solid fa-video")
        BonusFeature.objects.create(plan=starter, label="Support Slack", icon_class="fa-solid fa-comments")

        params = dict(self.params)
        params.update(
            {
                "bonus_icons": {
                    "enabled": True,
                    "plan_slug": "starter",
                    "visible_count": 1,
                    "title": "Bonus inclus",
                }
            }
        )

        ctx = pricing_packs(None, params)
        self.assertIn("plans", ctx)
        starter_ctx = next(plan for plan in ctx["plans"] if plan["slug"] == "starter")
        self.assertIsNotNone(starter_ctx.get("bonus_icons"))
        items_visible = starter_ctx["bonus_icons"]["items_visible"]
        self.assertEqual(len(items_visible), 1)
        self.assertEqual(items_visible[0]["label"], "Atelier live")


class PricingIntegrationTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.factory = RequestFactory()
        PricePlan.objects.update_or_create(
            slug="starter",
            defaults={
                "title": "Starter Integration",
                "price_cents": 2900,
                "currency": "€",
                "features": ["Acces integration"],
                "priority": 1,
                "is_active": True,
            },
        )
        PricePlan.objects.update_or_create(
            slug="createur",
            defaults={
                "title": "Createur Integration",
                "price_cents": 27900,
                "currency": "€",
                "priority": 2,
                "is_active": True,
            },
        )

    def test_online_home_renders_db_plan_labels(self) -> None:
        request = self.factory.get("/")
        request.site_version = "core"

        page_ctx = pipeline.build_page_spec("online_home", request)
        slot_ctx = page_ctx["slots"]["pricing_pack"]
        badges = slot_ctx.setdefault("params", {}).setdefault("badges", {})
        limited = badges.setdefault("limited_offer", {})
        if limited.get("deadline_ts") is None:
            limited["deadline_ts"] = ""
        fragment = pipeline.render_slot_fragment(page_ctx, slot_ctx, request)
        html = fragment.get("html", "")

        self.assertIn("Starter Integration", html)
        self.assertIn("Createur Integration", html)
        self.assertNotIn("premium-pro", html)


class AnalyticsConsentTemplateTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.factory = RequestFactory()
        MarketingGlobal.objects.all().delete()
        cache.delete(CFG_CACHE_KEY)

    def tearDown(self) -> None:
        cache.delete(CFG_CACHE_KEY)
        super().tearDown()

    def _render_base(self, request):
        cache.delete(CFG_CACHE_KEY)
        context = seo(request)
        base_ctx = {
            "tracking": context["tracking"],
            "marketing_config": context["marketing_config"],
            "page_assets": {"head": [], "css": [], "js": []},
            "slots_html": {
                "vendors": "",
                "header": "",
                "header_struct": "",
                "footer": "",
                "footer_main": "",
            },
            "messages": [],
        }
        return render_to_string("base.html", context=base_ctx, request=request)

    @override_settings(ANALYTICS_ENABLED=True)
    def test_bootstrap_script_included_when_analytics_enabled(self) -> None:
        request = self.factory.get("/")
        html = self._render_base(request)
        self.assertIn("analytics_bootstrap", html)
        self.assertNotIn("site/analytics.js", html)

    @override_settings(ANALYTICS_ENABLED=False)
    def test_bootstrap_script_not_rendered_when_disabled(self) -> None:
        request = self.factory.get("/")
        html = self._render_base(request)
        self.assertNotIn("analytics_bootstrap", html)

    @override_settings(ANALYTICS_ENABLED=True)
    def test_body_attribute_uses_configured_cookie_name(self) -> None:
        request = self.factory.get("/")
        html = self._render_base(request)
        self.assertIn('data-ll-consent-cookie="cookie_consent_marketing"', html)

    def test_auto_consent_cookie_middleware_sets_cookie_when_disabled(self) -> None:
        client = Client()
        original_flag = getattr(settings, "COOKIE_MANAGER_ENABLED", True)
        try:
            settings.COOKIE_MANAGER_ENABLED = False
            response = client.get("/")
            consent_name = getattr(settings, "CONSENT_COOKIE_NAME", "cookie_consent_marketing")
            self.assertIn(consent_name, response.cookies)
            self.assertEqual(response.cookies[consent_name].value, "true")
        finally:
            settings.COOKIE_MANAGER_ENABLED = original_flag


class ConsentDebugHeadersMiddlewareTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.factory = RequestFactory()

    @override_settings(CONSENT_DEBUG_HEADERS=False)
    def test_headers_absent_when_disabled(self) -> None:
        middleware = ConsentDebugHeadersMiddleware(lambda request: HttpResponse(status=204))
        request = self.factory.get("/")
        request.COOKIES[settings.CONSENT_COOKIE_NAME] = "1"

        response = middleware(request)

        self.assertNotIn("X-Consent-Marketing-Name", response)
        self.assertNotIn("X-Analytics-Bootstrap", response)

    @override_settings(CONSENT_DEBUG_HEADERS=True)
    def test_headers_present_when_enabled(self) -> None:
        middleware = ConsentDebugHeadersMiddleware(lambda request: HttpResponse(status=204))
        request = self.factory.get("/")
        request.COOKIES[settings.CONSENT_COOKIE_NAME] = "1"

        response = middleware(request)

        self.assertEqual(response["X-Consent-Marketing-Name"], settings.CONSENT_COOKIE_NAME)
        self.assertEqual(response["X-Consent-Marketing-Value"], "1")
        self.assertIn("analytics_bootstrap.js", response["X-Analytics-Bootstrap"])
