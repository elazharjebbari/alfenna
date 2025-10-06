# apps/pages/views/views_course_detail.py
from __future__ import annotations
from typing import Dict, Any
from django.http import Http404
from django.urls import reverse, NoReverseMatch
from django.views.generic import TemplateView

from apps.atelier.compose import pipeline, response
from apps.catalog.models import Course
from apps.content.models import Lecture
from apps.billing.models import Entitlement  # si tu veux distinguer “owner”

class CourseDetailView(TemplateView):
    template_name = "screens/fallback.html"  # écran défini par ton composeur

    def _first_lecture_url(self, course: Course) -> str:
        # 1) d’abord une free, sinon la 1ère publiée
        lec = (
            Lecture.objects.filter(course=course, is_published=True, is_free=True)
            .select_related("section").order_by("section__order", "order").first()
            or Lecture.objects.filter(course=course, is_published=True)
            .select_related("section").order_by("section__order", "order").first()
        )
        if lec:
            # essaie la route pages:lecture-detail avec un slug “léger” (optionnel)
            slug_part = f"s{lec.section.order}-l{lec.order}"
            try:
                return reverse("pages:lecture-detail", kwargs={"course_slug": course.slug, "lecture_slug": slug_part})
            except NoReverseMatch:
                pass
        # fallback propre (la view “learn” choisit la première leçon)
        return reverse("pages:lecture", kwargs={"course_slug": course.slug})

    def _compute_access(self, request, course: Course) -> Dict[str, Any]:
        if not request.user.is_authenticated:
            return {
                "state": "guest",
                "first_url": "",  # n/a
                "checkout_url": reverse("billing:checkout", kwargs={"slug": course.slug}),
                "login_url": reverse("pages:login") + f"?next={course.get_absolute_url()}",
                "note": "Paiement invité possible.",
            }

        # connecté : à toi de choisir la règle.
        # 1) simple: tout connecté => accès direct aux leçons
        # 2) stricte: il faut un Entitlement :
        has_rights = Entitlement.objects.filter(user=request.user, course=course).exists()
        if has_rights:
            return {"state": "owner", "first_url": self._first_lecture_url(course)}
        # sinon “member” (connecté sans achat)
        return {
            "state": "member",
            "first_url": self._first_lecture_url(course),  # si tu veux proposer “Commencer”
            "checkout_url": reverse("billing:checkout", kwargs={"slug": course.slug}),
            "note": "",
        }

    def get(self, request, *args, **kwargs):
        slug = kwargs.get("course_slug") or kwargs.get("slug")
        course = Course.objects.published().filter(slug=slug).first()
        if not course:
            raise Http404("Cours introuvable")

        page_id = "course_detail"
        access = self._compute_access(request, course)

        # ↙️ on pousse les extras dans les params du composeur (merge non cassant)
        page_ctx = pipeline.build_page_spec(page_id, request, extra={"course_slug": course.slug, "access": access})

        fragments = {}
        for slot_id, slot_ctx in (page_ctx.get("slots") or {}).items():
            r = pipeline.render_slot_fragment(page_ctx, slot_ctx, request)
            fragments[slot_id] = r.get("html", "")

        assets = pipeline.collect_page_assets(page_ctx)
        return response.render_base(page_ctx, fragments, assets, request)
