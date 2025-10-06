# apps/billing/views.py
from __future__ import annotations
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST
from apps.catalog.models.models import Course
from apps.billing.services import PaymentService, PriceService

# NEW
from apps.marketing.rendering import render_with_meta

@login_required
def checkout_view(request, slug: str):
    course = get_object_or_404(Course, slug=slug, is_published=True)
    currency = PriceService.select_currency(request.GET.get('currency'))
    email = request.user.email or ""

    order, payload = PaymentService.create_or_update_order_and_intent(
        user=request.user,
        email=email,
        course=course,
        currency=currency,
    )
    context = {
        "course": course,
        "currency": currency,
        "amount_total": order.amount_total,
        "client_secret": payload["client_secret"],
        "stripe_publishable_key": payload["publishable_key"],
    }

    # SEO: noindex strict pour une page de checkout
    return render_with_meta(
        request,
        "billing/checkout.html",
        context,
        title=f"Paiement — {course.title}",
        description="Finalisez votre paiement en toute sécurité.",
        object_type="website",
        noindex=True,
        jsonld=None,  # (option) ajouter un JSON-LD "Order" si voulu plus tard
    )

@require_POST
@login_required
def refresh_intent(request, slug: str):
    course = get_object_or_404(Course, slug=slug, is_published=True)
    currency = PriceService.select_currency(request.POST.get('currency'))
    email = request.user.email or ""
    order, payload = PaymentService.create_or_update_order_and_intent(
        user=request.user,
        email=email,
        course=course,
        currency=currency,
    )
    return JsonResponse({
        "client_secret": payload["client_secret"],
        "publishable_key": payload["publishable_key"],
        "amount": order.amount_total,
        "currency": order.currency
    })