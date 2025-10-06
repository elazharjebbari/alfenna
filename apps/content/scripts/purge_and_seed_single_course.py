# apps/content/scripts/purge_and_seed_single_course.py
# -*- coding: utf-8 -*-
"""
Purge TOTALE de tous les cours puis seed d'un SEUL cours depuis media/videos/stream/{fr_france,ar_maroc}.
- Multi-langues MP4 (fr_FR / ar_MA)
- Démo: 1, 1-1, 2, 2-1 (free)
- Vérifie l'existence réelle des fichiers (default_storage.exists)
Usage:
  export DJANGO_SETTINGS_MODULE=alfenna.settings.test_cli
  python manage.py runscript apps.content.scripts.purge_and_seed_single_course --script-args "slug=bougies-naturelles title='Bougies naturelles' --apply"
Dry-run (sans écrire):
  python manage.py runscript apps.content.scripts.purge_and_seed_single_course --script-args "slug=bougies-naturelles"
"""
from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from django.conf import settings
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils.text import slugify

from apps.catalog.models.models import Course
from apps.content.models import (
    Lecture, LectureType, Section,
    LectureVideoVariant, LanguageCode,
)
from apps.common.runscript_harness import binary_harness

FR_DIR = "videos/stream/fr_france"
AR_DIR = "videos/stream/ar_maroc"

FREE_PREFIXES = {"1", "1-1", "2", "2-1"}  # démo ouverte
SECTION_DEFINITION = {
    1: {"title": "Introduction et présentation du matériel",
        "prefixes": ["1", "1-1", "2", "2-1", "3", "3-1", "4", "4-1", "5", "5-1"]},
    2: {"title": "Formules et calculs", "prefixes": ["6", "6-1"]},
    3: {"title": "Pratique", "prefixes": ["7", "7-1", "8", "8-1", "9", "9-1"]},
    4: {"title": "Bonus", "prefixes": ["10", "11", "12", "13", "14"]},
}
PREFIX_RE = re.compile(r"^(?P<prefix>\d+(?:-\d+)?)[\s_\-]+(?P<title>.*)$")

@dataclass
class PrefixInfo:
    prefix: str
    title: str
    paths: Dict[str, str] = field(default_factory=dict)  # lang -> storage_path
    used: bool = False

def _parse_args(argv: Iterable[str] | None) -> Dict[str, str]:
    out = {"slug": "bougies-naturelles", "title": "Bougies naturelles", "apply": "0"}
    tokens = shlex.split(" ".join(argv or ()))
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok == "--apply":
            out["apply"] = "1"
            i += 1
            continue
        if "=" in tok:
            k, v = tok.split("=", 1)
            out[k.strip()] = v.strip()
        i += 1
    return out

def _pretty_title(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return "Leçon"
    # espaces propres, accents ok
    raw = re.sub(r"\s+", " ", raw)
    return raw[:200]

def _extract_prefix_and_title(stem: str) -> Optional[Tuple[str, str]]:
    m = PREFIX_RE.match(stem.strip())
    if not m:
        return None
    prefix = m.group("prefix")
    title = _pretty_title(m.group("title"))
    return prefix, title

def _collect(media_root: Path) -> Dict[str, PrefixInfo]:
    """Ne prend que des .mp4 sous stream/fr_france et stream/ar_maroc"""
    index: Dict[str, PrefixInfo] = {}
    for lang, subdir in (("fr_FR", FR_DIR), ("ar_MA", AR_DIR)):
        base = (media_root / subdir).resolve()
        if not base.exists():
            continue
        for p in sorted(base.glob("*.mp4")):
            rel = str(p.relative_to(media_root)).replace("\\", "/")
            parsed = _extract_prefix_and_title(p.stem)
            if not parsed:
                continue
            prefix, title = parsed
            info = index.setdefault(prefix, PrefixInfo(prefix=prefix, title=title))
            info.paths[lang] = rel
    return index

def _order_prefixes(infos: Dict[str, PrefixInfo]) -> List[str]:
    ordered: List[str] = []
    for section in SECTION_DEFINITION.values():
        for pref in section["prefixes"]:
            if pref in infos:
                ordered.append(pref)
    remaining = [p for p in infos.keys() if p not in ordered]
    remaining.sort(key=lambda x: [int(t) for t in x.split("-")])
    return ordered + remaining

def _assign_section(prefix: str) -> int:
    for s, meta in SECTION_DEFINITION.items():
        if prefix in meta["prefixes"]:
            return s
    return 4  # bonus par défaut

def _exists_storage(storage_path: str) -> bool:
    try:
        return default_storage.exists(storage_path)
    except Exception:
        return False

def _check_paths(infos: Dict[str, PrefixInfo]) -> Tuple[List[str], List[str]]:
    ok, missing = [], []
    for pref, info in infos.items():
        for lang, spath in info.paths.items():
            if _exists_storage(spath):
                ok.append(f"{pref} [{lang}] → {spath}")
            else:
                missing.append(f"{pref} [{lang}] ✖ missing → {spath}")
    return ok, missing

@binary_harness
@transaction.atomic
def run(*args, **kwargs):
    """
    Supporte:
      - run("--apply", "slug=bougies-naturelles", "title=Bougies naturelles")
      - run(script_args="slug=... title='...' --apply")
    """
    # 1) Récupérer la chaîne d'arguments quelle que soit la façon dont le harness les transmet
    raw = None
    if "script_args" in kwargs and kwargs["script_args"] is not None:
        raw = kwargs["script_args"]
    elif args:
        # args peut être un tuple de tokens OU une unique chaîne
        raw = " ".join(str(x) for x in args if x is not None)

    # 2) Parser
    params = _parse_args(raw.split() if isinstance(raw, str) else raw)

    slug = params.get("slug", "bougies-naturelles")
    title = params.get("title", "Bougies naturelles")
    apply = params.get("apply") == "1"

    media_root = Path(settings.MEDIA_ROOT).resolve()
    infos = _collect(media_root)
    if not infos:
        return {"ok": False, "name": "purge_and_seed_single_course",
                "duration": 0.0, "logs": ["Aucune vidéo .mp4 trouvée sous videos/stream/{fr_france,ar_maroc}."]}

    ok_paths, missing_paths = _check_paths(infos)

    to_delete = Course.objects.count()

    ordered = _order_prefixes(infos)
    sections_plan = [(s, SECTION_DEFINITION[s]["title"]) for s in sorted(SECTION_DEFINITION.keys())]
    lectures_plan = []
    for pref in ordered:
        info = infos[pref]
        lectures_plan.append({
            "prefix": pref,
            "title": info.title,
            "is_free": pref in FREE_PREFIXES,
            "fr": info.paths.get("fr_FR"),
            "ar": info.paths.get("ar_MA"),
        })

    print(f"[PLAN] Purge courses: {to_delete} | Nouveau slug: {slug!r} title: {title!r}")
    print(f"[PLAN] Sections: {len(sections_plan)} | Lectures à créer: {len(lectures_plan)}")
    if missing_paths:
        print("[WARN] Fichiers manquants dans le storage:")
        for line in missing_paths:
            print(" -", line)

    if not apply:
        transaction.set_rollback(True)
        return {"ok": True, "name": "purge_and_seed_single_course", "duration": 0.0,
                "logs": [{"deleted_courses": to_delete, "sections": len(sections_plan),
                          "lectures": len(lectures_plan), "paths_ok": ok_paths, "paths_missing": missing_paths}]}

    # APPLY
    Course.objects.all().delete()  # CASCADE → sections, lectures, variants

    course = Course.objects.create(
        slug=slug, title=title, description="Cours auto-généré depuis videos/stream.",
        is_published=True, free_lectures_count=len(FREE_PREFIXES),
    )

    sections: Dict[int, Section] = {}
    for order, s_title in sections_plan:
        sections[order] = Section.objects.create(course=course, order=order, title=s_title, is_published=True)

    per_section_order: Dict[int, int] = {k: 0 for k in sections.keys()}
    created_variants = 0
    created_lectures = 0

    for item in lectures_plan:
        pref = item["prefix"]
        section_order = _assign_section(pref)
        per_section_order[section_order] += 1

        fallback_path = item["fr"] or item["ar"] or ""

        lec = Lecture.objects.create(
            course=course, section=sections[section_order],
            order=per_section_order[section_order], type=LectureType.VIDEO,
            title=item["title"], is_published=True,
            is_free=item["is_free"], is_demo=item["is_free"],
            video_path=fallback_path,
        )
        created_lectures += 1

        if item["fr"]:
            LectureVideoVariant.objects.update_or_create(
                lecture=lec, lang=LanguageCode.FR_FR,
                defaults={"storage_path": item["fr"], "is_default": True},
            )
            created_variants += 1
        if item["ar"]:
            LectureVideoVariant.objects.update_or_create(
                lecture=lec, lang=LanguageCode.AR_MA,
                defaults={"storage_path": item["ar"], "is_default": False},
            )
            created_variants += 1

    return {
        "ok": True,
        "name": "purge_and_seed_single_course",
        "duration": 0.0,
        "logs": [{
            "deleted_courses": to_delete,
            "course_slug": slug,
            "sections": len(sections_plan),
            "lectures": created_lectures,
            "variants": created_variants,
            "paths_ok_count": len(ok_paths),
            "paths_missing_count": len(missing_paths),
        }],
    }

