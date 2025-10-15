from __future__ import annotations

from typing import Iterable, Optional

from django.db import models


class StringTranslation(models.Model):
    STATUS_CHOICES = (
        ("draft", "Draft"),
        ("active", "Active"),
    )

    SOURCE_CHOICES = (
        ("manual", "Manual"),
        ("import", "Import"),
        ("seed", "Seed"),
    )

    model_label = models.CharField(max_length=160)
    object_id = models.CharField(max_length=64)
    field = models.CharField(max_length=80)
    language = models.CharField(max_length=10)
    text = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default="manual", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("model_label", "object_id", "field", "language")
        indexes = [
            models.Index(fields=("model_label", "object_id", "field", "language")),
        ]
        verbose_name = "string translation"
        verbose_name_plural = "string translations"

    def __str__(self) -> str:  # pragma: no cover - debug helper
        return f"{self.model_label}:{self.object_id}.{self.field} [{self.language}]"


class TranslatableMixin(models.Model):
    """
    Abstract helper for models that expose translatable string fields.
    """

    translatable_fields: Iterable[str] = ()

    class Meta:
        abstract = True

    def translation_identifier(self) -> str:
        slug = getattr(self, "slug", None)
        if slug:
            return str(slug)
        pk = getattr(self, "pk", None)
        return str(pk)

    def translation_key(self, field: str, suffix: Optional[str] = None) -> str:
        base = f"db:{self._meta.app_label}.{self._meta.model_name}:{self.translation_identifier()}:{field}"
        if suffix:
            return f"{base}.{suffix}"
        return base

    def preferred_site_version(self) -> str:
        return getattr(self, "site_version", "") or ""
