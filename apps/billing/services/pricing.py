from __future__ import annotations

from decimal import Decimal
from typing import Optional

from django.db import models
from django.utils import timezone

from apps.catalog.models.models import Course, CoursePrice
from apps.marketing.models.models_pricing import PricePlan

SUPPORTED_CURRENCIES = {"EUR", "USD"}
DEFAULT_CURRENCY = "EUR"


class PriceService:
    @staticmethod
    def select_currency(requested: str | None) -> str:
        cur = (requested or DEFAULT_CURRENCY).upper()
        return cur if cur in SUPPORTED_CURRENCIES else DEFAULT_CURRENCY

    @staticmethod
    def _now():
        return timezone.now()

    @staticmethod
    def resolve_course_price_cents(course: Course, currency: str, country: str | None = None) -> int:
        now = PriceService._now()
        qs = CoursePrice.objects.filter(
            course=course,
            currency=currency.upper(),
            active=True,
            effective_at__lte=now,
        ).filter(models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=now))

        if country:
            specific = qs.filter(country=country.upper()).order_by("-effective_at").first()
            if specific:
                return specific.amount_cents

        default = qs.filter(country__isnull=True).order_by("-effective_at").first()
        if default:
            return default.amount_cents

        raise ValueError(f"No active price for course={course.id} currency={currency} country={country}")

    @staticmethod
    def course_amount_cents(course: Course, currency: str, country: str | None = None) -> int:
        return PriceService.resolve_course_price_cents(course, currency, country)

    @staticmethod
    def compute_total_from_plan(plan: PricePlan, currency: str, coupon: str | None = None) -> dict:
        currency_code = PriceService.select_currency(currency)
        subtotal = int(getattr(plan, "price_cents", 0) or 0)
        tax_amount = 0
        total = subtotal + tax_amount
        list_price_cents = int(getattr(plan, "old_price_cents", 0) or subtotal)

        discount_pct = Decimal("0.00")
        if list_price_cents and list_price_cents > subtotal:
            diff = list_price_cents - subtotal
            discount_pct = (
                Decimal(diff) / Decimal(list_price_cents) * Decimal("100")
            ).quantize(Decimal("0.01"))

        return {
            "currency": currency_code,
            "amount_subtotal": subtotal,
            "tax_amount": tax_amount,
            "amount_total": total,
            "list_price_cents": list_price_cents,
            "discount_pct": discount_pct,
            "final_amount_cents": total,
            "coupon": coupon or "",
        }


__all__ = ["PriceService", "SUPPORTED_CURRENCIES", "DEFAULT_CURRENCY"]
