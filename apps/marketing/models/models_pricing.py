from __future__ import annotations
from django.db import models

class PricePlan(models.Model):
    slug = models.SlugField(unique=True)
    title = models.CharField(max_length=120)
    currency = models.CharField(max_length=8, default="€")
    currency_symbol = models.CharField(max_length=8, default="€")
    price_cents = models.PositiveIntegerField(default=0)
    old_price_cents = models.PositiveIntegerField(null=True, blank=True)
    ribbon_label = models.CharField(max_length=60, blank=True, default="")
    is_featured = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    display_order = models.IntegerField(default=0)
    priority = models.IntegerField(default=0)

    features = models.JSONField(default=list, blank=True)
    value_breakdown = models.JSONField(default=list, blank=True)

    # CTA fields
    cta_label = models.CharField(max_length=80, blank=True, default="")
    cta_url = models.URLField(blank=True, default="")
    cta_sublabel = models.CharField(max_length=140, blank=True, default="")
    cta_aria = models.CharField(max_length=140, blank=True, default="")

    # Optional second CTA
    second_cta_label = models.CharField(max_length=80, blank=True, default="")
    second_cta_url = models.URLField(blank=True, default="")
    second_cta_aria = models.CharField(max_length=140, blank=True, default="")

    payment_note = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        ordering = ["priority", "display_order", "id"]

    def __str__(self) -> str:
        return f"{self.title} ({self.slug})"

    def get_currency(self) -> str:
        return (self.currency or self.currency_symbol or "€").strip() or "€"

    def get_features(self) -> list:
        return list(self.features or [])

    def get_value_breakdown(self) -> list:
        return list(self.value_breakdown or [])

    def save(self, *args, **kwargs):
        if not self.currency:
            self.currency = self.currency_symbol or "€"
        if not self.currency_symbol:
            self.currency_symbol = self.currency or "€"
        super().save(*args, **kwargs)


class PriceFeature(models.Model):
    plan = models.ForeignKey(PricePlan, on_delete=models.CASCADE)
    label = models.CharField(max_length=160)
    included = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self) -> str:
        return f"{self.plan.slug} – {self.label}"


class PriceBonusItem(models.Model):
    plan = models.ForeignKey(PricePlan, on_delete=models.CASCADE)
    label = models.CharField(max_length=160)
    amount_cents = models.PositiveIntegerField(default=0)
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self) -> str:
        return f"{self.plan.slug} – {self.label}"


# NEW — BonusFeature (Starter spotlight avec icônes)
class BonusFeature(models.Model):
    """
    Bonus non monétisés, iconifiés, destinés au spotlight d’un plan (Starter).
    Ex. "Réaliser une bougie deux couleurs", icône=fa-solid fa-fill-drip
    """
    plan = models.ForeignKey(PricePlan, on_delete=models.CASCADE, related_name="bonusfeature_set")
    label = models.CharField(max_length=160)
    icon_class = models.CharField(
        max_length=80,
        blank=True,
        default="",   # ex: "fa-solid fa-fill-drip" ou "icofont-flora-flower"
        help_text="Classe CSS d’icône (Font Awesome / Icofont / Flaticon)."
    )
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self) -> str:
        return f"{self.plan.slug} – {self.label}"
