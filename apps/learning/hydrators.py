from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.urls import reverse
from django.utils.functional import cached_property

from apps.content.models import Lecture
from apps.atelier.compose.hydrators.learning.hydrators import resolve_stream_url

_PLACEHOLDER_POSTER = getattr(settings, "LEARNING_PLACEHOLDER_POSTER", "https://placehold.co/960x540")
_FALLBACK_CACHE: dict[bool, dict] = {}
_FALLBACK_PATH = Path(settings.BASE_DIR) / "lumierelearning" / "fixtures" / "course_bougies_fallback.yml"
_DEFAULT_UI = {
    "program_heading": "Parcours pédagogique",
    "demo_heading": "Sélection de démonstration",
    "empty_message": "Aucun contenu disponible pour le moment.",
}


@dataclass
class LectureInfo:
    lecture: Lecture
    is_demo_only: bool

    @cached_property
    def video_url(self) -> str | None:
        url = resolve_stream_url(self.lecture)
        if url:
            return url
        return reverse("learning:stream", args=[self.lecture.pk])

    @cached_property
    def poster_url(self) -> str:
        return _PLACEHOLDER_POSTER


def _fallback_payload(demo_only: bool) -> dict:
    if demo_only in _FALLBACK_CACHE:
        return _FALLBACK_CACHE[demo_only]
    if not _FALLBACK_PATH.exists():
        _FALLBACK_CACHE[demo_only] = {}
        return {}
    import yaml

    data = yaml.safe_load(_FALLBACK_PATH.read_text(encoding="utf-8")) or {}
    if demo_only:
        filtered_sections = []
        for section in data.get("sections", []):
            lectures = [lec for lec in section.get("lectures", []) if lec.get("is_demo")]
            if lectures:
                filtered_sections.append({**section, "lectures": lectures})
        data = {**data, "sections": filtered_sections}
    data.setdefault("ui", dict(_DEFAULT_UI))
    # keep only relevant heading for demo context
    if demo_only:
        data["ui"]["program_heading"] = _DEFAULT_UI["demo_heading"]
    _FALLBACK_CACHE[demo_only] = data
    return data


def hydrate_course_content(course_slug: str, *, demo_only: bool = False) -> dict:
    lecture_qs = (
        Lecture.objects.filter(course__slug=course_slug, is_published=True)
        .select_related("section", "course")
        .order_by("section__order", "order", "id")
    )
    if demo_only:
        lecture_qs = lecture_qs.filter(is_demo=True)

    lectures = list(lecture_qs)
    if not lectures:
        return _fallback_payload(demo_only)

    course = lectures[0].course

    sections_map: dict[int, dict] = {}
    if lectures:
        for lec in lectures:
            if not lec.section_id:
                continue
            sec = lec.section
            if sec.id not in sections_map:
                sections_map[sec.id] = {
                    "id": sec.id,
                    "title": sec.title,
                    "order": sec.order,
                    "lectures": [],
                }
            info = LectureInfo(lecture=lec, is_demo_only=demo_only)
            sections_map[sec.id]["lectures"].append(
                {
                    "id": lec.id,
                    "title": lec.title,
                    "order": lec.order,
                    "video_url": info.video_url,
                    "poster_url": info.poster_url,
                    "is_demo": bool(lec.is_demo),
                }
            )

    sections = sorted(sections_map.values(), key=lambda section: section["order"])

    if demo_only and sections:
        sections = [
            {**section, "lectures": [lec for lec in section["lectures"] if lec["is_demo"]]}
            for section in sections
        ]
        sections = [section for section in sections if section["lectures"]]

    context = {
        "course": {
            "id": course.id,
            "title": course.title,
            "slug": course.slug,
            "description": course.description,
        },
        "sections": sections,
        "ui": dict(_DEFAULT_UI),
    }
    if demo_only:
        context["ui"]["program_heading"] = _DEFAULT_UI["demo_heading"]
    return context


def fallback_course_content(demo_only: bool = False) -> dict:
    return _fallback_payload(demo_only)
