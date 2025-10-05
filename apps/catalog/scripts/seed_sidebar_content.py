# apps/atelier/scripts/seed_sidebar_content.py
from __future__ import annotations
from django.db import transaction
from apps.catalog.models import Course
from apps.catalog.models import CourseSidebarSettings, SidebarInfoItem, SidebarBundleItem
from apps.common.runscript_harness import binary_harness

@binary_harness
def run(*args, **kwargs):
    created = 0
    for c in Course.objects.filter(is_published=True).order_by("id"):
        with transaction.atomic():
            ss, was = CourseSidebarSettings.objects.get_or_create(
                course=c,
                defaults={
                    "currency": "MAD",
                    "promo_badge": "Lancement",
                    "bundle_title": "Pack conversion",
                    "cta_guest_label": "Accéder au paiement",
                    "cta_member_label": "Connexion",
                    "cta_note": "Paiement invité possible.",
                },
            )
            created += 1 if was else 0

            if not ss.info_items.exists():
                SidebarInfoItem.objects.bulk_create([
                    SidebarInfoItem(settings=ss, order=1, icon="icofont-ui-video-play", label="Vidéos", value="9 modules"),
                    SidebarInfoItem(settings=ss, order=2, icon="icofont-clock-time", label="Durée", value="04h30"),
                ])
            if not ss.bundle_items.exists():
                SidebarBundleItem.objects.bulk_create([
                    SidebarBundleItem(settings=ss, order=1, text="Séquences e-mails"),
                    SidebarBundleItem(settings=ss, order=2, text="Checklist UX"),
                ])
    print(f"seed_sidebar_content: OK (created={created})")
    return {"ok": True}
