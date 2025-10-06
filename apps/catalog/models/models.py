from __future__ import annotations
import uuid
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

class CourseQuerySet(models.QuerySet):
    def published(self):
        return self.filter(is_published=True)

class Course(models.Model):
    DIFFICULTY_CHOICES = [
        ("beginner", "Débutant"),
        ("intermediate", "Intermédiaire"),
        ("advanced", "Avancé"),
    ]

    course_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True)
    description = models.TextField(blank=True)

    # SEO
    seo_title = models.CharField(max_length=70, blank=True)
    seo_description = models.CharField(max_length=160, blank=True)
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

    objects = CourseQuerySet.as_manager()

    class Meta:
        ordering = ['-published_at', '-created_at']
        indexes = [
            models.Index(fields=['slug']),
        ]

    def __str__(self) -> str:
        return self.title

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