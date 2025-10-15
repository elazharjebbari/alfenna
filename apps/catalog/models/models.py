from __future__ import annotations
import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.utils import translation
from parler.managers import TranslatableManager, TranslatableQuerySet
from parler.models import TranslatableModel, TranslatedFields

from apps.i18n.models import TranslatableMixin


class ProductQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class Product(TranslatableMixin):
    class MediaKind(models.TextChoices):
        HERO = "hero", "Hero"
        GALLERY = "gallery", "Gallery"
        LIFESTYLE = "lifestyle", "Lifestyle"

    translatable_fields = (
        "name",
        "subname",
        "description",
        "highlights",
        "badges",
        "offers",
        "testimonials",
        "cross_sells",
    )

    slug = models.SlugField(max_length=220, unique=True)
    name = models.CharField(max_length=180)
    subname = models.CharField(max_length=300, null=True, blank=True)
    description = models.TextField(blank=True)
    highlights = models.JSONField(default=list, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    promo_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default="MAD")
    is_active = models.BooleanField(default=True)
    seo_title = models.CharField(max_length=160, blank=True)
    seo_description = models.CharField(max_length=320, blank=True)
    extra = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ProductQuerySet.as_manager()

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name or self.slug


class ProductBadge(models.Model):
    product = models.ForeignKey("catalog.Product", on_delete=models.CASCADE, related_name="badges")
    text = models.CharField(max_length=120)
    icon = models.CharField(max_length=120, blank=True)
    extra = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.text} ({self.product.slug})"


class ProductImage(models.Model):
    product = models.ForeignKey("catalog.Product", on_delete=models.CASCADE, related_name="images")
    kind = models.CharField(max_length=16, choices=Product.MediaKind.choices, default=Product.MediaKind.GALLERY)
    src = models.URLField(max_length=500)
    alt = models.CharField(max_length=255, blank=True)
    thumb = models.URLField(max_length=500, blank=True)
    position = models.PositiveIntegerField(default=0)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self) -> str:
        return f"{self.product.slug}#{self.position}"


class ProductOption(models.Model):
    product = models.ForeignKey("catalog.Product", on_delete=models.CASCADE, related_name="options")
    key = models.SlugField(max_length=50)
    label = models.CharField(max_length=120)
    enabled = models.BooleanField(default=True)
    items = models.JSONField(default=list, blank=True)
    extra = models.JSONField(default=dict, blank=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]
        unique_together = ("product", "key")

    def __str__(self) -> str:
        return f"{self.product.slug}:{self.key}"


class ProductOffer(models.Model):
    product = models.ForeignKey("catalog.Product", on_delete=models.CASCADE, related_name="offers")
    code = models.SlugField(max_length=50)
    title = models.CharField(max_length=160)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    compare_at_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_featured = models.BooleanField(default=False)
    savings_label = models.CharField(max_length=120, blank=True)
    extra = models.JSONField(default=dict, blank=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]
        unique_together = ("product", "code")

    def __str__(self) -> str:
        return f"{self.product.slug}:{self.code}"


class TestimonialMedia(models.Model):
    product = models.ForeignKey("catalog.Product", on_delete=models.CASCADE, related_name="testimonial_media")
    author = models.CharField(max_length=160, blank=True)
    quote = models.TextField(blank=True)
    image_url = models.URLField(max_length=500, blank=True)
    video_url = models.URLField(max_length=500, blank=True)
    position = models.PositiveIntegerField(default=0)
    extra = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self) -> str:
        return f"testimonial:{self.product.slug}:{self.position}"


class CourseQuerySet(TranslatableQuerySet):
    _translation_fields = {"title", "description", "seo_title", "seo_description"}

    def _rewrite_translation_kwargs(self, kwargs: dict) -> dict:
        rewritten = {}
        for key, value in kwargs.items():
            base_key = key.split("__", 1)[0]
            if base_key in self._translation_fields:
                rewritten[f"translations__{key}"] = value
            else:
                rewritten[key] = value
        return rewritten

    def _rewrite_q(self, node: Q) -> Q:
        children = []
        for child in node.children:
            if isinstance(child, Q):
                children.append(self._rewrite_q(child))
            elif isinstance(child, tuple):
                key, value = child
                base_key = key.split("__", 1)[0]
                if base_key in self._translation_fields:
                    children.append((f"translations__{key}", value))
                else:
                    children.append(child)
            else:
                children.append(child)
        node.children = children
        return node

    def _filter_or_exclude(self, negate, *args, **kwargs):
        if kwargs:
            kwargs = self._rewrite_translation_kwargs(kwargs)
        if args:
            new_args = []
            for arg in args:
                if isinstance(arg, Q):
                    new_args.append(self._rewrite_q(arg))
                elif isinstance(arg, dict):
                    new_args.append(self._rewrite_translation_kwargs(arg))
                else:
                    new_args.append(arg)
            args = tuple(new_args)
        return super()._filter_or_exclude(negate, *args, **kwargs)

    def published(self):
        return self.filter(is_published=True)


class CourseManager(TranslatableManager.from_queryset(CourseQuerySet)):

    def get_queryset(self):
        qs = super().get_queryset()
        lang = translation.get_language() or getattr(settings, "PARLER_DEFAULT_LANGUAGE_CODE", None)
        if lang:
            qs = qs.active_translations(lang)
        return qs


class Course(TranslatableModel):
    DIFFICULTY_CHOICES = [
        ("beginner", "Débutant"),
        ("intermediate", "Intermédiaire"),
        ("advanced", "Avancé"),
    ]

    course_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    slug = models.SlugField(max_length=220, unique=True)
    translations = TranslatedFields(
        title=models.CharField(max_length=200),
        description=models.TextField(blank=True),
        seo_title=models.CharField(max_length=70, blank=True),
        seo_description=models.CharField(max_length=160, blank=True),
    )
    image = models.ImageField(upload_to='course_images/', blank=True, null=True)

    difficulty = models.CharField(max_length=16, choices=DIFFICULTY_CHOICES, default="beginner")

    # Gating Phase 3 (prévu ici)
    free_lectures_count = models.PositiveSmallIntegerField(default=0)

    # Publication
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(blank=True, null=True)

    # Cache plan versioning
    plan_version = models.PositiveIntegerField(default=1)

    # Traces
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CourseManager()

    class Meta:
        ordering = ['-published_at', '-created_at']

    def __str__(self) -> str:
        return self.safe_translation_getter("title", default=self.slug or str(self.pk))

    def clean(self):
        # Slug immuable si déjà publié
        if self.pk:
            old = Course.objects.filter(pk=self.pk).values('slug', 'is_published').first()
            if old and old['is_published'] and old['slug'] != self.slug:
                raise ValidationError({'slug': "Le slug est immuable après publication."})

        # SEO fallbacks
        if not self.seo_title:
            self.seo_title = self.title[:70]
        if not self.seo_description and self.description:
            self.seo_description = (self.description or '')[:160]

    def save(self, *args, **kwargs):
        creating = self.pk is None
        if creating and not self.slug:
            self.slug = slugify(self.title)[:220]
        if self.is_published and not self.published_at:
            self.published_at = timezone.now()
        # Validation stricte
        self.full_clean()
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse('pages:course-detail', args=[self.slug])

class CoursePrice(models.Model):
    CURRENCIES = [
        ("EUR", "Euro"),
        ("USD", "US Dollar"),
        ("MAD", "DHS Marocain"),
    ]
    course = models.ForeignKey("catalog.Course", on_delete=models.CASCADE, related_name="prices")
    currency = models.CharField(max_length=3, choices=CURRENCIES)
    # ISO 3166-1 alpha-2 ou Null pour prix “par défaut” dans la devise
    country = models.CharField(max_length=2, null=True, blank=True)
    amount_cents = models.PositiveIntegerField()
    active = models.BooleanField(default=True)
    effective_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["course", "currency", "country", "active", "effective_at", "expires_at"]),
        ]
        # Unicité “douce”: on ne peut pas empêcher en DB les overlaps temporels,
        # mais on peut exiger qu’il n’existe pas deux entrées strictement identiques.
        constraints = [
            models.UniqueConstraint(
                fields=["course", "currency", "country", "effective_at"],
                name="uniq_courseprice_keyslice",
            ),
        ]

    def __str__(self):
        where = self.country or "default"
        return f"{self.course.slug} {self.currency} {self.amount_cents}c [{where}]"
