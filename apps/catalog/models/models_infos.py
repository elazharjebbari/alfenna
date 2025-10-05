# apps/catalog/models/models_info.py
from __future__ import annotations
from django.db import models

# ---------- TRAINING (bloc principal de la fiche cours) ----------

class CourseTrainingContent(models.Model):
    course = models.OneToOneField(
        "catalog.Course", on_delete=models.CASCADE, related_name="training_content"
    )

    hero_image_url = models.URLField(blank=True, default="")
    hero_tag = models.CharField(max_length=120, blank=True, default="")
    video_url = models.URLField(blank=True, default="")
    video_label = models.CharField(max_length=120, blank=True, default="")

    title = models.CharField(max_length=200, blank=True, default="")
    subtitle = models.CharField(max_length=300, blank=True, default="")
    enrollment_label = models.CharField(max_length=200, blank=True, default="")

    rating_value = models.FloatField(default=0.0)               # 0..5
    rating_percentage = models.PositiveSmallIntegerField(default=0)  # 0..100, 0=auto
    rating_count = models.PositiveIntegerField(default=0)

    description_title = models.CharField(max_length=120, blank=True, default="")
    bundle_title = models.CharField(max_length=120, blank=True, default="")
    curriculum_title = models.CharField(max_length=120, blank=True, default="")
    instructors_title = models.CharField(max_length=120, blank=True, default="")
    reviews_title = models.CharField(max_length=120, blank=True, default="")

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Contenu Training (cours)"

    def __str__(self) -> str:
        return f"TrainingContent({self.course.slug})"


class TrainingDescriptionBlock(models.Model):
    training = models.ForeignKey(CourseTrainingContent, on_delete=models.CASCADE, related_name="description_blocks")
    content = models.TextField()
    order = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["order", "id"]


class TrainingBundleItem(models.Model):
    training = models.ForeignKey(CourseTrainingContent, on_delete=models.CASCADE, related_name="bundle_items")
    text = models.CharField(max_length=300)
    order = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["order", "id"]


class TrainingCurriculumSection(models.Model):
    training = models.ForeignKey(CourseTrainingContent, on_delete=models.CASCADE, related_name="curriculum_sections")
    title = models.CharField(max_length=200)
    order = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["order", "id"]


class TrainingCurriculumItem(models.Model):
    section = models.ForeignKey(TrainingCurriculumSection, on_delete=models.CASCADE, related_name="items")
    text = models.CharField(max_length=300)
    order = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["section", "order", "id"]


class TrainingInstructor(models.Model):
    training = models.ForeignKey(CourseTrainingContent, on_delete=models.CASCADE, related_name="instructors")
    name = models.CharField(max_length=120)
    role = models.CharField(max_length=120, blank=True, default="")
    profile_url = models.URLField(blank=True, default="")
    avatar_url = models.URLField(blank=True, default="")
    bio = models.TextField(blank=True, default="")
    order = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["order", "id"]


class TrainingReview(models.Model):
    training = models.ForeignKey(CourseTrainingContent, on_delete=models.CASCADE, related_name="reviews")
    author = models.CharField(max_length=120)
    location = models.CharField(max_length=120, blank=True, default="")
    content = models.TextField()
    avatar_url = models.URLField(blank=True, default="")
    order = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["order", "id"]


# ---------- SIDEBAR (panneau latéral) ----------

class CourseSidebarSettings(models.Model):
    course = models.OneToOneField(
        "catalog.Course", on_delete=models.CASCADE, related_name="sidebar_settings"
    )
    currency = models.CharField(max_length=10, default="MAD")
    promo_badge = models.CharField(max_length=100, blank=True, default="")

    bundle_title = models.CharField(max_length=120, blank=True, default="")
    cta_guest_label = models.CharField(max_length=120, blank=True, default="Acheter sans inscription")
    cta_member_label = models.CharField(max_length=120, blank=True, default="Se connecter pour continuer")
    cta_note = models.CharField(max_length=300, blank=True, default="")

    # Override optionnels (laisse vide pour defaults compute_promotion_price)
    price_override = models.PositiveIntegerField(null=True, blank=True)
    discount_pct_override = models.PositiveSmallIntegerField(null=True, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Réglages Sidebar (cours)"

    def __str__(self) -> str:
        return f"SidebarSettings({self.course.slug})"


class SidebarInfoItem(models.Model):
    settings = models.ForeignKey(CourseSidebarSettings, on_delete=models.CASCADE, related_name="info_items")
    icon = models.CharField(max_length=120, blank=True, default="")
    label = models.CharField(max_length=120, blank=True, default="")
    value = models.CharField(max_length=200, blank=True, default="")
    order = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["order", "id"]


class SidebarBundleItem(models.Model):
    settings = models.ForeignKey(CourseSidebarSettings, on_delete=models.CASCADE, related_name="bundle_items")
    text = models.CharField(max_length=300)
    order = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["order", "id"]


class LinkKind(models.TextChoices):
    REVERSE = "reverse", "Reverse by name"
    EXTERNAL = "external", "External URL"


class SidebarLink(models.Model):
    class Role(models.TextChoices):
        GUEST = "guest", "Guest CTA"
        MEMBER = "member", "Member CTA"

    settings = models.ForeignKey(CourseSidebarSettings, on_delete=models.CASCADE, related_name="links")
    role = models.CharField(max_length=12, choices=Role.choices)
    kind = models.CharField(max_length=12, choices=LinkKind.choices, default=LinkKind.REVERSE)

    # reverse
    url_name = models.CharField(max_length=200, blank=True, default="")
    url_kwargs = models.JSONField(default=dict, blank=True)

    # external
    external_url = models.URLField(blank=True, default="")

    append_next = models.BooleanField(default=False)

    class Meta:
        unique_together = (("settings", "role"),)

    def __str__(self) -> str:
        return f"{self.settings.course.slug} [{self.role}]"
