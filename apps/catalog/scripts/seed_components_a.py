# apps/atelier/scripts/seed_components_a.py
from __future__ import annotations
from django.db import transaction
from django.utils import timezone

from apps.common.runscript_harness import binary_harness
from apps.catalog.models import Course
from apps.content.models import Section, Lecture
from apps.catalog.models import (
    CourseTrainingContent, TrainingDescriptionBlock, TrainingBundleItem,
    TrainingCurriculumSection, TrainingCurriculumItem, TrainingInstructor, TrainingReview,
    CourseSidebarSettings, SidebarInfoItem, SidebarBundleItem, SidebarLink, LinkKind
)

@binary_harness
def run(*args, **kwargs):
    print("== seed_components_a: start ==")
    created_tc = created_ss = 0

    for course in Course.objects.filter(is_published=True).order_by("id"):
        with transaction.atomic():
            # --- TRAINING ---
            tc, was = CourseTrainingContent.objects.get_or_create(
                course=course,
                defaults={
                    "title": course.title,
                    "subtitle": (course.seo_description or course.description)[:300],
                    "description_title": "Description",
                    "bundle_title": "Bundle exclusif",
                    "curriculum_title": "Programme",
                    "instructors_title": "Formateurs",
                    "reviews_title": "Avis",
                    "rating_value": 4.8,
                    "rating_percentage": 0,   # 0 => auto
                    "rating_count": 1250,
                    "enrollment_label": "+500 apprenants satisfaits",
                },
            )
            created_tc += 1 if was else 0

            if not tc.description_blocks.exists():
                TrainingDescriptionBlock.objects.bulk_create([
                    TrainingDescriptionBlock(training=tc, order=1, content="Découvrez comment créer des bougies uniques pas à pas."),
                    TrainingDescriptionBlock(training=tc, order=2, content="Approfondissez votre savoir-faire avec des modules vidéo détaillés."),
                ])

            if not tc.bundle_items.exists():
                TrainingBundleItem.objects.bulk_create([
                    TrainingBundleItem(training=tc, order=1, text="Accès illimité à la bibliothèque vidéo"),
                    TrainingBundleItem(training=tc, order=2, text="Guide PDF téléchargeable"),
                    TrainingBundleItem(training=tc, order=3, text="Support communauté pendant 30 jours"),
                ])

            # Curriculum à partir des sections/lectures existantes
            if not tc.curriculum_sections.exists():
                for sec in Section.objects.filter(course=course, is_published=True).order_by("order"):
                    s = TrainingCurriculumSection.objects.create(training=tc, order=sec.order, title=sec.title or f"Module {sec.order}")
                    items = Lecture.objects.filter(section=sec, is_published=True).order_by("order").values_list("title", "order")
                    TrainingCurriculumItem.objects.bulk_create([
                        TrainingCurriculumItem(section=s, order=o or i+1, text=t or f"Leçon {i+1}")
                        for i, (t, o) in enumerate(items)
                    ])

            if not tc.instructors.exists():
                TrainingInstructor.objects.create(
                    training=tc, order=1,
                    name="Souheila Jebbari", role="Formatrice principale",
                    bio="Spécialiste des bougies naturelles."
                )

            if not tc.reviews.exists():
                TrainingReview.objects.bulk_create([
                    TrainingReview(training=tc, order=1, author="Salma", location="Tanger", content="Une formation inspirante avec un excellent suivi."),
                    TrainingReview(training=tc, order=2, author="Mehdi", location="Fès", content="Parcours structuré et concret pour lancer son activité."),
                ])

            # --- SIDEBAR ---
            ss, was2 = CourseSidebarSettings.objects.get_or_create(
                course=course,
                defaults={
                    "currency": "MAD",
                    "promo_badge": "Promo spéciale",
                    "bundle_title": "Bonus inclus",
                    "cta_guest_label": "Acheter sans inscription",
                    "cta_member_label": "Se connecter pour continuer",
                    "cta_note": "Achat possible en mode invité",
                },
            )
            created_ss += 1 if was2 else 0

            if not ss.info_items.exists():
                SidebarInfoItem.objects.bulk_create([
                    SidebarInfoItem(settings=ss, order=1, icon="icofont-man-in-glasses", label="Formatrice", value="Souheila Jebbari"),
                    SidebarInfoItem(settings=ss, order=2, icon="icofont-clock-time", label="Durée", value="06h00"),
                    SidebarInfoItem(settings=ss, order=3, icon="icofont-ui-video-play", label="Vidéos", value="30 modules"),
                    SidebarInfoItem(settings=ss, order=4, icon="icofont-book-alt", label="Langue", value="🇲🇦 / 🇫🇷"),
                ])

            if not ss.bundle_items.exists():
                SidebarBundleItem.objects.bulk_create([
                    SidebarBundleItem(settings=ss, order=1, text="Accès communauté privée"),
                    SidebarBundleItem(settings=ss, order=2, text="Réductions sur les ateliers présentiels"),
                ])

            # Liens CTA (LinkSpec)
            links = {ln.role: ln for ln in ss.links.all()}
            if "guest" not in links:
                SidebarLink.objects.create(
                    settings=ss, role=SidebarLink.Role.GUEST, kind=LinkKind.REVERSE,
                    url_name="billing:checkout", url_kwargs={"slug": "<course.slug>"},
                    append_next=False,
                )
            if "member" not in links:
                SidebarLink.objects.create(
                    settings=ss, role=SidebarLink.Role.MEMBER, kind=LinkKind.REVERSE,
                    url_name="accounts:login", url_kwargs={},
                    append_next=True,   # next = checkout
                )

    print(f"seed_components_a: OK — training_created={created_tc}, sidebar_created={created_ss}")
    return {"ok": True, "name": "seed_components_a", "created_tc": created_tc, "created_ss": created_ss}
