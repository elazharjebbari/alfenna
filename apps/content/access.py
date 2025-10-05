# apps/content/access.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from django.db.models import Q
from django.http import HttpRequest
from apps.catalog.models.models import Course
from apps.content.models import Lecture

@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    reason: str
    status: int = 200  # 200 ok, 403 premium lock, 404 unpublished

class AccessPolicy:
    """
    Politique d’accès centralisée.
    Règles:
      - Staff + preview=1 => accès total (non indexé côté SEO, géré dans les templates/vue)
      - Leçon/cours non publié => 404 public (staff preview ok)
      - Utilisateur avec droit (Phase 4) => accès total
      - Sinon, accès si rang_de_la_leçon_dans_le_cours <= course.free_lectures_count
    """
    def __init__(self, request: HttpRequest) -> None:
        self.request = request

    def _has_preview(self) -> bool:
        return bool(self.request.user.is_staff and self.request.GET.get("preview"))

    # def _has_entitlement(self, course: Course) -> bool:
    #     """Hook P4 Billing. Pour les tests, on permet une simulation via la session."""
    #     user = self.request.user
    #     if not user.is_authenticated:
    #         return False
    #     if getattr(user, "is_superuser", False):
    #         return True
    #     course_ids = set(self.request.session.get("entitled_course_ids", []))
    #     return course.id in course_ids

    def _has_entitlement(self, course: Course) -> bool:
        user = self.request.user
        if not user.is_authenticated:
            return False
        if getattr(user, "is_superuser", False):
            return True

        # Fallback test/simulation via session (utilisé par les harness Phase 0).
        session = getattr(self.request, "session", None)
        if session is not None:
            course_ids = session.get("entitled_course_ids", []) or []
            normalized = {str(cid) for cid in course_ids}
            if str(course.id) in normalized:
                return True

        # Import local pour éviter cycles et rester souple si billing n'est pas migré.
        try:
            from apps.billing.models import Entitlement
        except Exception:
            return False

        try:
            return Entitlement.objects.filter(user=user, course=course).exists()
        except Exception:
            # En phase de tests, se contente de retourner False si la table n'est pas prête.
            return False

    def _lecture_rank_in_course(self, lecture: Lecture) -> int:
        """Calcule le rang global de la leçon dans le cours (1..N) via DB.
        On compte les leçons publiées dont (section.order < S) ou (section=S et order <= L).
        """
        qs = Lecture.objects.filter(course=lecture.course, is_published=True)
        qs = qs.filter(
            Q(section__order__lt=lecture.section.order) |
            (Q(section__order=lecture.section.order) & Q(order__lte=lecture.order))
        )
        return qs.count()

    def can_view(self, lecture: Lecture) -> AccessDecision:
        course = lecture.course
        preview = self._has_preview()

        # Unpublished handling
        if not course.is_published or not lecture.is_published:
            if preview:
                return AccessDecision(True, "preview_staff")
            return AccessDecision(False, "unpublished", 404)

        # Entitlement (P4-ready)
        if self._has_entitlement(course):
            return AccessDecision(True, "entitled")

        # Free quota
        free_n = int(getattr(course, "free_lectures_count", 0) or 0)
        if free_n > 0:
            rank = self._lecture_rank_in_course(lecture)
            if rank <= free_n:
                return AccessDecision(True, "free_quota")

        return AccessDecision(False, "premium_locked", 403)

def can_access_lecture(user, course, lecture, request: Optional[HttpRequest] = None):
    """
    Petit adaptateur pour les mixins: renvoie (allowed, reason)
    Utilise AccessPolicy pour garantir une seule source de vérité.
    """
    if request is None:
        # best-effort: faux request minimal (pas de preview sans GET)
        req = HttpRequest()
        req.user = user
        req.GET = {}
    else:
        req = request
    decision = AccessPolicy(req).can_view(lecture)
    return decision.allowed, decision.reason
