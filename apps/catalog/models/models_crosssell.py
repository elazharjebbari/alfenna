from __future__ import annotations

from django.db import models

from .models import Product


class ComplementaryProduct(models.Model):
    """Standalone product that can be attached as a cross-sell item."""

    slug = models.SlugField(max_length=220, unique=True)
    title = models.CharField(max_length=180)
    short_description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    promo_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=8, default="MAD")
    image_src = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)
    extra = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("title", "slug")

    def __str__(self) -> str:
        return self.title or self.slug


class ProductCrossSell(models.Model):
    """Relation between catalog product and complementary product."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="cross_sells")
    complementary = models.ForeignKey(
        ComplementaryProduct, on_delete=models.CASCADE, related_name="attached_to"
    )
    position = models.PositiveIntegerField(default=0)
    label_override = models.CharField(max_length=120, blank=True)
    extra = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("product", "complementary")
        ordering = ("position", "id")

    def __str__(self) -> str:
        return f"{self.product.slug} -> {self.complementary.slug}"
