# apps/atelier/scripts/tweak_components_variants.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Iterable, List, Dict

from django.db import transaction
from django.utils import timezone

from apps.common.runscript_harness import binary_harness
from apps.catalog.models import Course
from apps.catalog.models import (
    CourseTrainingContent, TrainingDescriptionBlock, TrainingBundleItem,
    TrainingCurriculumSection, TrainingCurriculumItem, TrainingInstructor, TrainingReview,
    CourseSidebarSettings, SidebarInfoItem, SidebarBundleItem, SidebarLink, LinkKind
)


@dataclass
class TrainingSpec:
    title: str | None = None
    subtitle: str | None = None
    hero_tag: str | None = None
    video_url: str | None = None
    video_label: str | None = None
    rating_value: float | None = None
    rating_count: int | None = None
    enrollment_label: str | None = None
    description_blocks: List[str] = field(default_factory=list)
    bundle_items: List[str] = field(default_factory=list)
    instructors: List[Dict] = field(default_factory=list)  # [{name, role, bio, avatar_url?}]
    reviews: List[Dict] = field(default_factory=list)      # [{author, location, content, avatar_url?}]


@dataclass
class SidebarSpec:
    currency: str | None = None
    promo_badge: str | None = None
    price_override: int | None = None         # MAD/EUR selon ton site
    discount_pct_override: int | None = None
    bundle_title: str | None = None
    info_items: List[Dict] = field(default_factory=list)   # [{icon,label,value}]
    bundle_items: List[str] = field(default_factory=list)
    cta_guest_label: str | None = None
    cta_member_label: str | None = None
    cta_note: str | None = None


# === Overrides ciblés par slug (ajuste les clés aux slugs réels de ta base) ===
OVERRIDES: dict[str, dict[str, object]] = {
    "stream-demo": {
        "training": TrainingSpec(
            hero_tag="Streaming avancé",
            subtitle="Validez le Range 206, sécurisez le flux et observez vos métriques.",
            rating_value=4.7, rating_count=980,
            enrollment_label="+900 apprenants",
            description_blocks=[
                "Découvrez les fondations du streaming progressif.",
                "Bonnes pratiques de sécurité et monitoring.",
            ],
            bundle_items=[
                "Gabarits Nginx prêts à l’emploi",
                "Playbooks Ansible",
            ],
            instructors=[{"name": "Souheila Jebbari", "role": "Formatrice principale",
                          "bio": "Experte production & observabilité."}],
            reviews=[{"author": "Imane", "location": "Casablanca",
                      "content": "Parfait pour industrialiser rapidement."}],
        ),
        "sidebar": SidebarSpec(
            currency="MAD", promo_badge="-25% cette semaine",
            price_override=None, discount_pct_override=25,
            bundle_title="Livrables inclus",
            info_items=[
                {"icon": "icofont-ui-video-play", "label": "Vidéos", "value": "12 modules"},
                {"icon": "icofont-shield-alt", "label": "Sécurité", "value": "Guides inclus"},
            ],
            bundle_items=["Templates Nginx", "Dashboards Grafana"],
            cta_guest_label="Tester et payer",
            cta_member_label="Me connecter",
            cta_note="Accès immédiat après paiement.",
        ),
    },
    "gating-demo": {
        "training": TrainingSpec(
            hero_tag="Gating & Accès libre",
            subtitle="Mix gratuit/premium avec quotas intelligents.",
            rating_value=4.5, rating_count=720,
            enrollment_label="+650 apprenants",
            description_blocks=[
                "Donner envie avec des cours gratuits sans cannibaliser le premium.",
                "Stratégies de conversion éprouvées.",
            ],
            bundle_items=["Exemples d’e-mails", "Segments analytics"],
            instructors=[{"name": "Naila Baiga", "role": "Experte design",
                          "bio": "Onboarding & UX de conversion."}],
            reviews=[{"author": "Younes", "location": "Rabat",
                      "content": "A vu +30% de conversion sur mon site."}],
        ),
        "sidebar": SidebarSpec(
            currency="MAD", promo_badge="Lancement",
            discount_pct_override=30,
            info_items=[
                {"icon": "icofont-ui-video-play", "label": "Vidéos", "value": "9 modules"},
                {"icon": "icofont-clock-time", "label": "Durée", "value": "04h30"},
            ],
            bundle_title="Pack conversion",
            bundle_items=["Sequences e-mails", "Checklist UX"],
            cta_guest_label="Accéder au paiement",
            cta_member_label="Connexion",
            cta_note="Paiement invité possible.",
        ),
    },
    # Ajoute ici d'autres slugs si besoin…
}


def _ensure_links(ss: CourseSidebarSettings):
    """Crée/garantit les CTA configurables (LinkSpec)."""
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


def _replace_collection(qs, create_fn: callable, items: Iterable):
    qs.all().delete()
    if not items:
        return
    create_fn(items)


@binary_harness
def run(*args, **kwargs):
    """
    Utilisation:
      python manage.py runscript apps.atelier.scripts.tweak_components_variants
      python manage.py runscript apps.atelier.scripts.tweak_components_variants --script-args reset
      python manage.py runscript apps.atelier.scripts.tweak_components_variants --script-args slug=stream-demo
    """
    reset = ("reset" in args) or kwargs.get("reset") in (True, "1", "true", "True")
    only_slug = kwargs.get("slug")

    updated_tc = created_tc = updated_ss = created_ss = 0

    courses = Course.objects.filter(is_published=True).order_by("id")
    if only_slug:
        courses = courses.filter(slug=only_slug)

    for idx, course in enumerate(courses):
        spec = OVERRIDES.get(course.slug, {})
        t_spec: TrainingSpec | None = spec.get("training")  # type: ignore
        s_spec: SidebarSpec | None = spec.get("sidebar")    # type: ignore

        with transaction.atomic():
            # ---------- TRAINING ----------
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
                    "rating_value": 4.6 + (idx % 3) * 0.1,  # variation douce si pas override
                    "rating_percentage": 0,
                    "rating_count": 700 + idx * 50,
                    "enrollment_label": f"+{500 + idx*80} apprenants",
                },
            )
            created_tc += 1 if was else 0

            # MàJ champs simples si override présent
            if t_spec:
                for f, v in (
                    ("title", t_spec.title or course.title),
                    ("subtitle", t_spec.subtitle or tc.subtitle),
                    ("hero_tag", t_spec.hero_tag or tc.hero_tag),
                    ("video_url", t_spec.video_url or tc.video_url),
                    ("video_label", t_spec.video_label or tc.video_label),
                    ("rating_value", t_spec.rating_value or tc.rating_value),
                    ("rating_count", t_spec.rating_count or tc.rating_count),
                    ("enrollment_label", t_spec.enrollment_label or tc.enrollment_label),
                ):
                    setattr(tc, f, v)
                tc.save(update_fields=[
                    "title", "subtitle", "hero_tag", "video_url", "video_label",
                    "rating_value", "rating_count", "enrollment_label", "updated_at"
                ])
                updated_tc += 1

                # Collections (on remplace si reset ou si override spécifique fourni)
                if reset or t_spec.description_blocks:
                    _replace_collection(
                        tc.description_blocks,
                        lambda items: TrainingDescriptionBlock.objects.bulk_create(
                            [TrainingDescriptionBlock(training=tc, order=i+1, content=txt) for i, txt in enumerate(items)]
                        ),
                        t_spec.description_blocks,
                    )
                if reset or t_spec.bundle_items:
                    _replace_collection(
                        tc.bundle_items,
                        lambda items: TrainingBundleItem.objects.bulk_create(
                            [TrainingBundleItem(training=tc, order=i+1, text=txt) for i, txt in enumerate(items)]
                        ),
                        t_spec.bundle_items,
                    )
                if reset or t_spec.instructors:
                    _replace_collection(
                        tc.instructors,
                        lambda items: TrainingInstructor.objects.bulk_create(
                            [TrainingInstructor(training=tc, order=i+1, **data) for i, data in enumerate(items)]
                        ),
                        t_spec.instructors,
                    )
                if reset or t_spec.reviews:
                    _replace_collection(
                        tc.reviews,
                        lambda items: TrainingReview.objects.bulk_create(
                            [TrainingReview(training=tc, order=i+1, **data) for i, data in enumerate(items)]
                        ),
                        t_spec.reviews,
                    )

            # ---------- SIDEBAR ----------
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

            if s_spec:
                for f, v in (
                    ("currency", s_spec.currency or ss.currency),
                    ("promo_badge", s_spec.promo_badge or ss.promo_badge),
                    ("bundle_title", s_spec.bundle_title or ss.bundle_title),
                    ("cta_guest_label", s_spec.cta_guest_label or ss.cta_guest_label),
                    ("cta_member_label", s_spec.cta_member_label or ss.cta_member_label),
                    ("cta_note", s_spec.cta_note or ss.cta_note),
                    ("price_override", s_spec.price_override if s_spec.price_override is not None else ss.price_override),
                    ("discount_pct_override", s_spec.discount_pct_override if s_spec.discount_pct_override is not None else ss.discount_pct_override),
                ):
                    setattr(ss, f, v)
                ss.save(update_fields=[
                    "currency", "promo_badge", "bundle_title", "cta_guest_label",
                    "cta_member_label", "cta_note", "price_override",
                    "discount_pct_override", "updated_at"
                ])
                updated_ss += 1

                if reset or s_spec.info_items:
                    _replace_collection(
                        ss.info_items,
                        lambda items: SidebarInfoItem.objects.bulk_create(
                            [SidebarInfoItem(settings=ss, order=i+1, **data) for i, data in enumerate(items)]
                        ),
                        s_spec.info_items,
                    )
                if reset or s_spec.bundle_items:
                    _replace_collection(
                        ss.bundle_items,
                        lambda items: SidebarBundleItem.objects.bulk_create(
                            [SidebarBundleItem(settings=ss, order=i+1, text=txt) for i, txt in enumerate(items)]
                        ),
                        s_spec.bundle_items,
                    )

            _ensure_links(ss)

    print(f"tweak_components_variants: TC(created={created_tc}, updated={updated_tc}) "
          f"SS(created={created_ss}, updated={updated_ss})")
    return {
        "ok": True,
        "name": "tweak_components_variants",
        "tc_created": created_tc,
        "tc_updated": updated_tc,
        "ss_created": created_ss,
        "ss_updated": updated_ss,
    }
