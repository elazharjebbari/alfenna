# apps/pages/views.py
from __future__ import annotations

import logging
from django.http import Http404
from django.views.generic import TemplateView

from apps.atelier.compose import pipeline, response
from apps.catalog.models.models import Course
from apps.content.models import Lecture
from apps.atelier.compose.hydrators.learning.hydrators import _lecture_slug
from apps.marketing.mixins import SeoViewMixin

log = logging.getLogger("pages.home")


class HomeView(SeoViewMixin, TemplateView):
    """
    Page d'accueil branchée sur le composeur Atelier.

    - build_page_spec : résout les slots et la preview QA
    - render_slot_fragment : rend chaque fragment (cache fragment géré côté pipeline)
    - collect_page_assets : agrège les assets déclarés par les composants
    - response.render_base : choisit automatiquement screens/online_home.html si présent,
      sinon fallback sur base.html, et prépare le contexte (slots_html + page_assets)
    """
    template_name = "screens/fallback.html"  # utilisé si fallback base → screen explicite

    def get(self, request, *args, **kwargs):
        page_id = "online_home"

        # 1) Construction de la spec de page (slots/variants/cache_key/preview)
        page_ctx = pipeline.build_page_spec(page_id, request)

        # 2) Rendu de chaque slot (HIT/MISS déjà géré par le pipeline)
        fragments = {}
        for slot_id, slot_ctx in (page_ctx.get("slots") or {}).items():
            rendered = pipeline.render_slot_fragment(page_ctx, slot_ctx, request)
            fragments[slot_id] = rendered.get("html", "")

        # 3) Collecte des assets réellement utilisés par la page
        assets = pipeline.collect_page_assets(page_ctx)

        # 4) Assemblage final (TemplateResponse paresseuse, compatible middlewares)
        return response.render_base(page_ctx, fragments, assets, request)

class ContactView(SeoViewMixin, TemplateView):
    """
    Page d'accueil branchée sur le composeur Atelier.

    - build_page_spec : résout les slots et la preview QA
    - render_slot_fragment : rend chaque fragment (cache fragment géré côté pipeline)
    - collect_page_assets : agrège les assets déclarés par les composants
    - response.render_base : choisit automatiquement screens/online_home.html si présent,
      sinon fallback sur base.html, et prépare le contexte (slots_html + page_assets)
    """
    template_name = "screens/contact.html"  # utilisé si fallback base → screen explicite
    def get(self, request, *args, **kwargs):
        page_id = "contact"

        # 1) Construction de la spec de page (slots/variants/cache_key/preview)
        page_ctx = pipeline.build_page_spec(page_id, request)

        # 2) Rendu de chaque slot (HIT/MISS déjà géré par le pipeline)
        fragments = {}
        for slot_id, slot_ctx in (page_ctx.get("slots") or {}).items():
            rendered = pipeline.render_slot_fragment(page_ctx, slot_ctx, request)
            fragments[slot_id] = rendered.get("html", "")

        # 3) Collecte des assets réellement utilisés par la page
        assets = pipeline.collect_page_assets(page_ctx)

        # 4) Assemblage final (TemplateResponse paresseuse, compatible middlewares)
        return response.render_base(page_ctx, fragments, assets, request)

class CoursesView(SeoViewMixin, TemplateView):
    """
    Page d'accueil branchée sur le composeur Atelier.

    - build_page_spec : résout les slots et la preview QA
    - render_slot_fragment : rend chaque fragment (cache fragment géré côté pipeline)
    - collect_page_assets : agrège les assets déclarés par les composants
    - response.render_base : choisit automatiquement screens/online_home.html si présent,
      sinon fallback sur base.html, et prépare le contexte (slots_html + page_assets)
    """
    template_name = "screens/courses.html"  # utilisé si fallback base → screen explicite
    def get(self, request, *args, **kwargs):
        page_id = "courses"

        # 1) Construction de la spec de page (slots/variants/cache_key/preview)
        page_ctx = pipeline.build_page_spec(page_id, request)

        # 2) Rendu de chaque slot (HIT/MISS déjà géré par le pipeline)
        fragments = {}
        for slot_id, slot_ctx in (page_ctx.get("slots") or {}).items():
            rendered = pipeline.render_slot_fragment(page_ctx, slot_ctx, request)
            fragments[slot_id] = rendered.get("html", "")

        # 3) Collecte des assets réellement utilisés par la page
        assets = pipeline.collect_page_assets(page_ctx)

        # 4) Assemblage final (TemplateResponse paresseuse, compatible middlewares)
        return response.render_base(page_ctx, fragments, assets, request)

class TestView(SeoViewMixin, TemplateView):
    """
    Page d'accueil branchée sur le composeur Atelier.

    - build_page_spec : résout les slots et la preview QA
    - render_slot_fragment : rend chaque fragment (cache fragment géré côté pipeline)
    - collect_page_assets : agrège les assets déclarés par les composants
    - response.render_base : choisit automatiquement screens/online_home.html si présent,
      sinon fallback sur base.html, et prépare le contexte (slots_html + page_assets)
    """
    template_name = "screens/fallback.html"  # utilisé si fallback base → screen explicite

    def get(self, request, *args, **kwargs):
        page_id = "test"

        # 1) Construction de la spec de page (slots/variants/cache_key/preview)
        page_ctx = pipeline.build_page_spec(page_id, request)

        # 2) Rendu de chaque slot (HIT/MISS déjà géré par le pipeline)
        fragments = {}
        for slot_id, slot_ctx in (page_ctx.get("slots") or {}).items():
            rendered = pipeline.render_slot_fragment(page_ctx, slot_ctx, request)
            fragments[slot_id] = rendered.get("html", "")

        # 3) Collecte des assets réellement utilisés par la page
        assets = pipeline.collect_page_assets(page_ctx)

        # 4) Assemblage final (TemplateResponse paresseuse, compatible middlewares)
        return response.render_base(page_ctx, fragments, assets, request)

class PacksView(SeoViewMixin, TemplateView):
    """
    Page d'accueil branchée sur le composeur Atelier.

    - build_page_spec : résout les slots et la preview QA
    - render_slot_fragment : rend chaque fragment (cache fragment géré côté pipeline)
    - collect_page_assets : agrège les assets déclarés par les composants
    - response.render_base : choisit automatiquement screens/online_home.html si présent,
      sinon fallback sur base.html, et prépare le contexte (slots_html + page_assets)
    """
    template_name = "screens/fallback.html"  # utilisé si fallback base → screen explicite

    def get(self, request, *args, **kwargs):
        page_id = "packs"

        # 1) Construction de la spec de page (slots/variants/cache_key/preview)
        page_ctx = pipeline.build_page_spec(page_id, request)

        # 2) Rendu de chaque slot (HIT/MISS déjà géré par le pipeline)
        fragments = {}
        for slot_id, slot_ctx in (page_ctx.get("slots") or {}).items():
            rendered = pipeline.render_slot_fragment(page_ctx, slot_ctx, request)
            fragments[slot_id] = rendered.get("html", "")

        # 3) Collecte des assets réellement utilisés par la page
        assets = pipeline.collect_page_assets(page_ctx)

        # 4) Assemblage final (TemplateResponse paresseuse, compatible middlewares)
        return response.render_base(page_ctx, fragments, assets, request)


class FaqView(SeoViewMixin, TemplateView):
    """FAQ statique alimentée par le composeur Atelier."""

    template_name = "screens/fallback.html"

    def get(self, request, *args, **kwargs):
        page_id = "faq"

        page_ctx = pipeline.build_page_spec(page_id, request)

        fragments = {}
        for slot_id, slot_ctx in (page_ctx.get("slots") or {}).items():
            rendered = pipeline.render_slot_fragment(page_ctx, slot_ctx, request)
            fragments[slot_id] = rendered.get("html", "")

        assets = pipeline.collect_page_assets(page_ctx)

        return response.render_base(page_ctx, fragments, assets, request)


class ProductDetailView(SeoViewMixin, TemplateView):
    """Fiche produit orchestrée par Atelier."""

    template_name = "screens/product-detail.html"
    page_id = "product_detail"

    def get(self, request, *args, **kwargs):
        page_id = getattr(self, "page_id", "product_detail")
        request._product_slug = kwargs.get("product_slug")

        page_ctx = pipeline.build_page_spec(page_id, request)

        fragments = {}
        for slot_id, slot_ctx in (page_ctx.get("slots") or {}).items():
            rendered = pipeline.render_slot_fragment(page_ctx, slot_ctx, request)
            fragments[slot_id] = rendered.get("html", "")

        assets = pipeline.collect_page_assets(page_ctx)

        return response.render_base(page_ctx, fragments, assets, request)


class ProductDetailLandingView(ProductDetailView):
    page_id = "product_detail_landing"
    template_name = "screens/product_detail_landing.html"


class DemoView(SeoViewMixin, TemplateView):
    template_name = "screens/demo.html"
    slug_url_kwarg = "course_slug"
    default_course_slug = "bougies-naturelles"

    def get(self, request, *args, **kwargs):
        course_slug = kwargs.get(self.slug_url_kwarg) or self.default_course_slug
        course, lecture = self._demo_targets(course_slug)
        request._demo_only = True

        route_kwargs = {"course_slug": course.slug, "lecture_slug": _lecture_slug(lecture)}
        request._route_kwargs = route_kwargs
        resolver_match = getattr(request, "resolver_match", None)
        if resolver_match and isinstance(getattr(resolver_match, "kwargs", None), dict):
            resolver_match.kwargs.update(route_kwargs)

        page_ctx = pipeline.build_page_spec("demo", request, extra=route_kwargs)

        fragments = {}
        for slot_id, slot_ctx in (page_ctx.get("slots") or {}).items():
            rendered = pipeline.render_slot_fragment(page_ctx, slot_ctx, request)
            fragments[slot_id] = rendered.get("html", "")

        assets = pipeline.collect_page_assets(page_ctx)

        self.meta_title = f"Démo vidéo — {course.title}"
        self.meta_description = course.description or ""

        return response.render_base(page_ctx, fragments, assets, request)

    def _demo_targets(self, course_slug: str):
        try:
            course = Course.objects.get(slug=course_slug)
        except Course.DoesNotExist as exc:
            raise Http404("Demo course not found") from exc

        lecture_qs = (
            Lecture.objects.filter(course=course, is_published=True)
            .select_related("section")
            .order_by("section__order", "order")
        )
        lecture = lecture_qs.filter(is_demo=True).first() or lecture_qs.filter(is_free=True).first() or lecture_qs.first()
        if lecture is None:
            raise Http404("No lecture available for demo")
        return course, lecture

# class CourseDetailView(CourseSlugGuardMixin, SeoViewMixin, TemplateView):
#     """
#     Page d'accueil branchée sur le composeur Atelier.
#
#     - build_page_spec : résout les slots et la preview QA
#     - render_slot_fragment : rend chaque fragment (cache fragment géré côté pipeline)
#     - collect_page_assets : agrège les assets déclarés par les composants
#     - response.render_base : choisit automatiquement screens/online_home.html si présent,
#       sinon fallback sur base.html, et prépare le contexte (slots_html + page_assets)
#     """
#     template_name = "screens/fallback.html"  # utilisé si fallback base → screen explicite
#
#     def get(self, request, *args, **kwargs):
#         course = self.get_course()  # ← 404 si absent
#         page_ctx = pipeline.build_page_spec(
#             page_id="course_detail",
#             request=request,
#             extra={"course_slug": course.slug},   # utile aux hydrators.py
#         )
#
#         fragments = {}
#         for slot_id, slot_ctx in (page_ctx.get("slots") or {}).items():
#             rendered = pipeline.render_slot_fragment(page_ctx, slot_ctx, request)
#             fragments[slot_id] = rendered.get("html", "")
#
#         assets = pipeline.collect_page_assets(page_ctx)
#         return response.render_base(page_ctx, fragments, assets, request)




