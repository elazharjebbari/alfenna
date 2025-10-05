"""Reset and seed the Fabrication de bougies course with multilingual videos."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from django.conf import settings
from django.db import transaction

from apps.catalog.models.models import Course
from apps.content.models import Lecture, LectureType, Section, LectureVideoVariant, LanguageCode
from apps.common.runscript_harness import binary_harness


COURSE_SLUG = "fabrication-de-bougie"
COURSE_TITLE = "Fabrication de bougies"
FREE_PREFIXES = {"1", "1-1", "2", "2-1"}
FREE_LECTURES_COUNT = len(FREE_PREFIXES)

SECTION_DEFINITION = {
    1: {
        "title": "Introduction et présentation du matériel",
        "prefixes": ["1", "1-1", "2", "2-1", "3", "3-1", "4", "4-1", "5", "5-1"],
    },
    2: {
        "title": "Formules et calculs",
        "prefixes": ["6", "6-1"],
    },
    3: {
        "title": "Pratique",
        "prefixes": ["7", "7-1", "8", "8-1", "9", "9-1"],
    },
    4: {
        "title": "Bonus",
        "prefixes": ["10", "11", "12", "13", "14"],
    },
}


@dataclass
class PrefixInfo:
    prefix: str
    title: str
    primary_path: Optional[str] = None
    paths: Dict[str, str] = field(default_factory=dict)
    used: bool = False


def _prettify(raw: str) -> str:
    cleaned = raw.replace("_", " ").replace("-", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return "Leçon"
    return cleaned[:200]


_PREFIX_RE = re.compile(r"^(?P<prefix>\d+(?:-\d+)?)(?:[_\-\s]+)?(?P<title>.*)$")
_HASH_SUFFIX_RE = re.compile(r"([_-])([A-Za-z0-9]{4,})$")


def _strip_hash_suffix(value: str) -> str:
    candidate = value
    while candidate:
        match = _HASH_SUFFIX_RE.search(candidate)
        if not match:
            break
        token = match.group(2)
        if not any(ch.isdigit() for ch in token):
            break
        candidate = candidate[: match.start()]
    return candidate.rstrip(" _-")


def _extract_prefix(stem: str) -> Optional[tuple[str, str]]:
    base = stem.strip()
    match = _PREFIX_RE.match(base)
    if not match:
        return None
    prefix = match.group("prefix")
    raw_title = (match.group("title") or "")
    raw_title = _strip_hash_suffix(raw_title)
    raw_title = raw_title.strip(" _-")
    title = _prettify(raw_title) if raw_title else f"Leçon {prefix.replace('-', '.')}"
    return prefix, title


def _collect_prefix_infos(media_root: Path) -> Dict[str, PrefixInfo]:
    variant_dirs = {
        "fr_FR": ["videos/stream/fr_france"],
        "ar_MA": ["videos/strem/ar_maroc", "videos/stream/ar_maroc"],
    }
    index: Dict[str, PrefixInfo] = {}
    for lang, dirs in variant_dirs.items():
        for relative in dirs:
            base = (media_root / relative).resolve()
            if not base.exists() or not base.is_dir():
                continue
            for path in sorted(base.glob("*.mp4")):
                parsed = _extract_prefix(path.stem)
                if not parsed:
                    continue
                prefix, title = parsed
                rel_path = str(path.relative_to(media_root)).replace("\\", "/")
                info = index.setdefault(prefix, PrefixInfo(prefix=prefix, title=title))
                if lang == "fr_FR" and info.primary_path is None:
                    info.primary_path = rel_path
                info.paths[lang] = rel_path
    return index


def _ordered_prefixes(infos: Dict[str, PrefixInfo]) -> List[str]:
    ordered: List[str] = []
    for section in SECTION_DEFINITION.values():
        for prefix in section["prefixes"]:
            if prefix in infos:
                ordered.append(prefix)
    remaining = [p for p in infos.keys() if p not in ordered]
    if remaining:
        remaining.sort(key=lambda x: [int(part) for part in x.split("-")])
        ordered.extend(remaining)
    return ordered


def _create_sections(course: Course) -> Dict[int, Section]:
    sections: Dict[int, Section] = {}
    for order, meta in SECTION_DEFINITION.items():
        sections[order] = Section.objects.create(
            course=course,
            order=order,
            title=meta["title"],
            is_published=True,
        )
    return sections


def _assign_section(prefix: str) -> int:
    for section_order, meta in SECTION_DEFINITION.items():
        if prefix in meta["prefixes"]:
            return section_order
    return max(SECTION_DEFINITION.keys())


def _build_course(media_root: Path, infos: Dict[str, PrefixInfo]) -> Dict[str, object]:
    Course.objects.filter(slug=COURSE_SLUG).delete()
    course = Course.objects.create(
        title=COURSE_TITLE,
        slug=COURSE_SLUG,
        description="Parcours complet sur la fabrication artisanale de bougies.",
        is_published=True,
        free_lectures_count=FREE_LECTURES_COUNT,
    )
    sections = _create_sections(course)
    created_lectures = 0
    prefix_map: Dict[str, int] = {}
    per_section_order: Dict[int, int] = {order: 0 for order in sections}

    for prefix in _ordered_prefixes(infos):
        info = infos[prefix]
        section_order = _assign_section(prefix)
        section = sections[section_order]
        per_section_order[section_order] += 1
        lecture = Lecture.objects.create(
            course=course,
            section=section,
            order=per_section_order[section_order],
            title=info.title,
            type=LectureType.VIDEO,
            is_published=True,
            is_free=prefix in FREE_PREFIXES,
            is_demo=prefix in FREE_PREFIXES,
            video_path=info.primary_path or "",
        )
        info.used = True
        created_lectures += 1
        prefix_map[prefix] = lecture.id

    return {
        "course": course,
        "sections": len(sections),
        "lectures": created_lectures,
        "unused_prefixes": [p for p, info in infos.items() if not info.used],
        "prefix_map": prefix_map,
    }


@binary_harness
@transaction.atomic
def run(*, script_args: Iterable[str] | None = None):
    media_root = Path(settings.MEDIA_ROOT).resolve()
    infos = _collect_prefix_infos(media_root)
    if not infos:
        return {
            "ok": False,
            "name": "seed_bougie_multilang",
            "duration": 0.0,
            "logs": ["Aucun fichier vidéo trouvé sous MEDIA_ROOT."],
        }

    summary = _build_course(media_root, infos)

    prefix_map: Dict[str, int] = summary.get("prefix_map", {})
    for prefix, info in infos.items():
        lecture_id = prefix_map.get(prefix)
        if not lecture_id:
            continue
        fr_path = info.paths.get("fr_FR")
        ar_path = info.paths.get("ar_MA")
        if fr_path:
            LectureVideoVariant.objects.update_or_create(
                lecture_id=lecture_id,
                lang=LanguageCode.FR_FR,
                defaults={
                    "storage_path": fr_path,
                    "is_default": True,
                },
            )
        if ar_path:
            LectureVideoVariant.objects.update_or_create(
                lecture_id=lecture_id,
                lang=LanguageCode.AR_MA,
                defaults={
                    "storage_path": ar_path,
                    "is_default": False,
                },
            )

    unused = summary["unused_prefixes"]
    if unused:
        print(f"[WARN] Préfixes sans section dédiée: {', '.join(unused)}")

    return {
        "ok": True,
        "name": "seed_bougie_multilang",
        "duration": 0.0,
        "logs": [
            {
                "summary": summary,
            }
        ],
    }
