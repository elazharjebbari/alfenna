# apps/content/mixins.py
from __future__ import annotations
import logging
from django.contrib import messages
from django.http import Http404, HttpResponse, JsonResponse, HttpResponseForbidden
from django.shortcuts import redirect, get_object_or_404
from django.urls import reverse
from apps.catalog.models.models import Course
from apps.content.models import Lecture
from .access import AccessPolicy

from apps.content import access  # on réutilise la même politique centrale
from django.utils.translation import gettext as _

log = logging.getLogger("gating")

class GatedLectureAccessMixin:
    """Mixin à placer AVANT la CBV qui rend la leçon.
    S’occupe de: résolution des objets, décision d’accès, redirection 403/404.
    """
    course_kw = "course_slug"
    section_kw = "section_order"
    lecture_kw = "lecture_order"

    def _resolve_objects(self):
        from django.shortcuts import get_object_or_404
        course_slug = self.kwargs[self.course_kw]
        section_order = int(self.kwargs[self.section_kw])
        lecture_order = int(self.kwargs[self.lecture_kw])
        course = get_object_or_404(Course, slug=course_slug)
        lecture = get_object_or_404(
            Lecture.objects.select_related("section", "course"),
            course=course,
            section__order=section_order,
            order=lecture_order,
        )
        return course, lecture

    def dispatch(self, request, *args, **kwargs):
        course, lecture = self._resolve_objects()
        self.course = course
        self.lecture = lecture

        decision = AccessPolicy(request).can_view(lecture)

        log.info(
            "gating_decision user=%s course=%s lecture=%s/%s reason=%s status=%s",
            getattr(request.user, "id", None), course.id, lecture.section.order, lecture.order,
            decision.reason, decision.status,
        )

        if decision.allowed:
            return super().dispatch(request, *args, **kwargs)

        if decision.status == 404:
            raise Http404("Lecture non publiée")

        # 403 premium: redirection vers la page cours
        messages.warning(request, "Cette leçon est réservée. Accédez au cours pour la débloquer.")
        return redirect("catalog:detail", slug=course.slug)


class LectureAccessRequiredMixin:
    """
    À utiliser pour les vues non-HTML (POST/JSON) liées à une Lecture.
    - Résout self.lecture / self.course à partir de l'URL (pk).
    - Applique la même politique d'accès que GatedLectureAccessMixin (via apps.content.access).
    - Pour les requêtes JSON: renvoie 401/403 JSON propre.
    - Pour les flux HTML: redirige login / page du cours avec message.
    """

    login_url_name = "pages:login"          # redirection login si non authentifié (HTML)
    back_to_course_url_name = "catalog:course-detail"  # fallback si besoin pour HTML

    def _wants_json(self, request) -> bool:
        # fetch/XHR → JSON; notre script de progression attend du JSON
        return request.headers.get("x-requested-with") == "XMLHttpRequest" or \
               "application/json" in (request.headers.get("accept") or "")

    def dispatch(self, request, *args, **kwargs):
        # 1) Résoudre la leçon depuis l'URL (pk obligatoire ici)
        pk = kwargs.get("pk")
        lecture = get_object_or_404(Lecture, pk=pk)
        course = lecture.section.course

        self.lecture = lecture
        self.course = course

        # 2) Politique d’accès centralisée
        # On suppose une API du style: access.can_access_lecture(user, course, lecture) -> (allowed: bool, reason: str|None)
        allowed, reason = access.can_access_lecture(request.user, course, lecture)
        self.access_decision_reason = reason

        if allowed:
            log.info(
                "gating_decision user=%s course=%s lecture=%s/%s reason=%s status=200",
                getattr(request.user, "id", None),
                course.id,
                lecture.section.order,
                lecture.order,
                reason or "allowed",
            )
            return super().dispatch(request, *args, **kwargs)

        # 3) Non autorisé → JSON vs HTML
        if not request.user.is_authenticated:
            if self._wants_json(request):
                return JsonResponse({"detail": "authentication_required"}, status=401)
            login_url = reverse(self.login_url_name)
            return redirect(f"{login_url}?next={request.get_full_path()}")

        # Authentifié mais non autorisé (premium lock, etc.)
        log.info("gating_decision user=%s course=%s lecture=%s/%s reason=%s status=403",
                 getattr(request.user, "id", None), course.id, lecture.section.order, lecture.order, reason or "forbidden")

        if self._wants_json(request):
            return JsonResponse({"detail": reason or "forbidden"}, status=403)

        # Flux HTML (rare pour ces endpoints, mais propre)
        messages.error(request, _("Accès refusé à cette leçon."))
        try:
            return redirect(course.get_absolute_url())
        except Exception:
            return HttpResponseForbidden(_("Accès refusé."))
