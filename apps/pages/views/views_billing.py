# apps/pages/views/views_billing.py
from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.views.generic import View

from apps.atelier.compose import pipeline, response
from apps.billing.services import PriceService
from apps.catalog.models.models import Course
from apps.marketing.models.models_pricing import PricePlan


class CheckoutOrchestratorView(View):
    template_name = "screens/checkout.html"

    def get(self, request: HttpRequest, plan_slug: str) -> HttpResponse:
        price_plan = get_object_or_404(PricePlan, slug=plan_slug, is_active=True)
        currency = PriceService.select_currency(request.GET.get("currency"))
        totals = PriceService.compute_total_from_plan(price_plan, currency)

        course: Course | None = None
        course_id_param = request.GET.get("course_id")
        course_slug_param = (request.GET.get("course") or request.GET.get("course_slug") or "").strip()
        if course_id_param:
            course = get_object_or_404(Course, pk=course_id_param, is_published=True)
        elif course_slug_param:
            course = get_object_or_404(Course, slug=course_slug_param, is_published=True)
        if course is None:
            default_slug = getattr(settings, "DEFAULT_CHECKOUT_COURSE_SLUG", "bougies-naturelles")
            if default_slug:
                course = (
                    Course.objects.filter(slug=default_slug, is_published=True)
                    .only("id", "slug")
                    .first()
                )

        request._price_plan = price_plan  # for hydrators needing direct access
        request._checkout_course = course

        page_ctx = pipeline.build_page_spec(
            page_id="checkout",
            request=request,
            extra={
                "price_plan": price_plan,
                "plan_slug": price_plan.slug,
                "course": course,
                "course_slug": getattr(course, "slug", ""),
                "course_id": getattr(course, "id", None),
                "currency": currency,
                "amount_total_cents": totals.get("amount_total", totals.get("final_amount_cents")),
                "amount_subtotal_cents": totals.get("amount_subtotal"),
                "list_price_cents": totals.get("list_price_cents"),
                "discount_pct": totals.get("discount_pct"),
                "tax_amount_cents": totals.get("tax_amount", 0),
            },
        )

        fragments = {}
        for slot_id, slot_ctx in (page_ctx.get("slots") or {}).items():
            r = pipeline.render_slot_fragment(page_ctx, slot_ctx, request)
            fragments[slot_id] = r.get("html", "")

        assets = pipeline.collect_page_assets(page_ctx)

        return response.render_base(page_ctx, fragments, assets, request)


class ThankYouView(View):
    template_name = "screens/thank_you.html"

    def get(self, request: HttpRequest, plan_slug: str) -> HttpResponse:
        price_plan = get_object_or_404(PricePlan, slug=plan_slug, is_active=True)
        request._price_plan = price_plan
        request._checkout_course = None
        page_ctx = pipeline.build_page_spec(
            page_id="thank_you",
            request=request,
            extra={"price_plan": price_plan, "plan_slug": price_plan.slug},
        )
        fragments = {}
        for slot_id, slot_ctx in (page_ctx.get("slots") or {}).items():
            r = pipeline.render_slot_fragment(page_ctx, slot_ctx, request)
            fragments[slot_id] = r.get("html", "")
        assets = pipeline.collect_page_assets(page_ctx)
        return response.render_base(page_ctx, fragments, assets, request)
