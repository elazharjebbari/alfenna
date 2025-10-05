from __future__ import annotations
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

class Section(models.Model):
    course = models.ForeignKey('catalog.Course', related_name='sections', on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    order = models.PositiveIntegerField(default=1)
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('course', 'order')
        constraints = [
            models.UniqueConstraint(fields=['course', 'order'], name='unique_section_order_per_course'),
        ]

    def __str__(self) -> str:
        return f"{self.course.title} — {self.order}. {self.title}"

class LectureType(models.TextChoices):
    VIDEO = 'video', _('Vidéo')
    ARTICLE = 'article', _('Article')
    PDF = 'pdf', _('PDF/Document')
    LINK = 'link', _('Lien externe')


class LanguageCode(models.TextChoices):
    FR_FR = 'fr_FR', _('Français (France)')
    AR_MA = 'ar_MA', _('Arabe (Maroc)')

class Lecture(models.Model):
    course = models.ForeignKey('catalog.Course', related_name='lectures', on_delete=models.CASCADE)
    section = models.ForeignKey(Section, related_name='lectures', on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    order = models.PositiveIntegerField(default=1)
    type = models.CharField(max_length=16, choices=LectureType.choices, default=LectureType.ARTICLE)

    # Champs spécifiques par type (simples pour P0)
    video_file = models.FileField(upload_to='videos/', blank=True, null=True)
    video_path = models.CharField(max_length=500, blank=True, default="")
    document_file = models.FileField(upload_to='docs/', blank=True, null=True)
    external_url = models.URLField(blank=True, null=True)
    duration_seconds = models.PositiveIntegerField(blank=True, null=True)

    is_published = models.BooleanField(default=True)
    is_free = models.BooleanField(default=False)
    is_demo = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('section', 'order')
        constraints = [
            models.UniqueConstraint(fields=['section', 'order'], name='unique_lecture_order_per_section'),
        ]

    def get_absolute_url(self) -> str:
        """
        URL canonique prioritaire: /<course_slug>/s<section>/l<lecture>/
        Fallback: /lecture/<pk>/
        """
        try:
            return reverse(
                "content:lecture-detail",
                kwargs={
                    "course_slug": self.course.slug,
                    "section_order": self.section.order,
                    "lecture_order": self.order,
                },
            )
        except Exception:
            return reverse("content:lecture-detail-pk", args=[self.pk])

    def __str__(self) -> str:
        return f"{self.section} — {self.order}. {self.title}"


class LectureVideoVariant(models.Model):
    lecture = models.ForeignKey(Lecture, related_name='video_variants', on_delete=models.CASCADE)
    lang = models.CharField(max_length=8, choices=LanguageCode.choices)
    file = models.FileField(upload_to='videos/', blank=True, null=True)
    storage_path = models.CharField(max_length=500, blank=True, default="")
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('lecture', 'lang')
        constraints = [
            models.UniqueConstraint(fields=['lecture', 'lang'], name='unique_lecture_lang_variant'),
        ]

    def path_in_storage(self) -> str:
        if self.file:
            return self.file.name
        return (self.storage_path or '').strip().lstrip('/')

    def __str__(self) -> str:
        return f"LectureVideoVariant({self.lecture_id}, {self.lang})"
