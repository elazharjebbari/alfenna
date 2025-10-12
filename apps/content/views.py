# apps/content/views.py
from __future__ import annotations

import logging

from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, get_object_or_404
from django.urls import reverse
from django.views.generic import TemplateView

from .access import AccessPolicy
from .mixins import GatedLectureAccessMixin
from .models import Lecture
from ..learning.models import LectureComment, Progress

from django.utils.translation import gettext as _
from apps.marketing import schema as seo_schema

class LectureDetailView(GatedLectureAccessMixin, TemplateView):
    template_name = "content/lecture_detail.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        course = getattr(self, "course")
        lecture = getattr(self, "lecture")

        ctx["course"] = course
        ctx["lecture"] = lecture
        preview = bool(self.request.user.is_staff and self.request.GET.get("preview"))
        ctx["preview"] = preview
        # ↓ Ajouts Phase 5 (sans casser l’existant)
        ctx["player_src"] = reverse("learning:stream", args=[lecture.id])
        ctx["comments"] = (
            LectureComment.objects.filter(lecture=lecture, is_visible=True)
            .select_related("user")[:100]
        )
        if self.request.user.is_authenticated:
            ctx["user_progress"] = Progress.objects.filter(user=self.request.user, lecture=lecture).first()

        course_title = course.get_i18n("title")
        lecture_title = lecture.get_i18n("title")
        self.meta_title = f"{lecture_title} — {course_title}"
        self.meta_description = f"Leçon {lecture.section.order}.{lecture.order} du cours {course_title}"
        self.meta_type = "article"
        if preview:
            self.meta_noindex = True
        # JSON-LD article si publié
        if lecture.is_published and course.is_published and not preview:
            self.seo_jsonld = [seo_schema.article_schema(lecture, self.request)]
        return ctx


class LectureDetailPKView(TemplateView):
    """
    Fallback par PK pour afficher une leçon : /content/lecture/<pk>/
    - Résout self.course / self.lecture par PK
    - Applique la même politique d’accès (AccessPolicy) que GatedLectureAccessMixin
    - Rend le même template et le même contexte que LectureDetailView
    """
    template_name = "content/lecture_detail.html"

    def dispatch(self, request, *args, **kwargs):
        log = logging.getLogger("gating")

        # 1) Résolution objets
        pk = kwargs.get("pk")
        lecture = get_object_or_404(
            Lecture.objects.select_related("section", "course"),
            pk=pk,
        )
        course = lecture.course
        self.lecture = lecture
        self.course = course

        # 2) Politique d’accès centralisée (identique à GatedLectureAccessMixin)
        decision = AccessPolicy(request).can_view(lecture)
        log.info(
            "gating_decision user=%s course=%s lecture=%s/%s reason=%s status=%s",
            getattr(request.user, "id", None),
            course.id, lecture.section.order, lecture.order,
            decision.reason, decision.status,
        )

        if decision.allowed:
            return super().dispatch(request, *args, **kwargs)

        if decision.status == 404:
            raise Http404("Lecture non publiée")

        messages.warning(request, _("Cette leçon est réservée. Accédez au cours pour la débloquer."))
        return redirect("catalog:detail", slug=course.slug)

    def get_context_data(self, **kwargs):
        # Contexte aligné sur LectureDetailView pour ne rien casser
        ctx = super().get_context_data(**kwargs)
        course = getattr(self, "course")
        lecture = getattr(self, "lecture")

        ctx["course"] = course
        ctx["lecture"] = lecture
        preview = bool(self.request.user.is_staff and self.request.GET.get("preview"))
        ctx["preview"] = preview
        # Ajouts Phase 5 (player, commentaires, progression)
        ctx["player_src"] = reverse("learning:stream", args=[lecture.id])
        ctx["comments"] = (
            LectureComment.objects
            .filter(lecture=lecture, is_visible=True)
            .select_related("user")[:100]
        )
        if self.request.user.is_authenticated:
            ctx["user_progress"] = Progress.objects.filter(user=self.request.user, lecture=lecture).first()

        course_title = course.get_i18n("title")
        lecture_title = lecture.get_i18n("title")
        self.meta_title = f"{lecture_title} — {course_title}"
        self.meta_description = f"Leçon {lecture.section.order}.{lecture.order} du cours {course_title}"
        self.meta_type = "article"
        if preview:
            self.meta_noindex = True
        # JSON-LD article si publié
        if lecture.is_published and course.is_published and not preview:
            self.seo_jsonld = [seo_schema.article_schema(lecture, self.request)]
        return ctx
