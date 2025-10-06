"""Attach multilingual video variants to lectures based on files present on disk."""
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

from django.conf import settings
from django.db import transaction
from django.utils.text import slugify

from apps.catalog.models.models import Course
from apps.content.models import Lecture, LectureVideoVariant, LanguageCode
from apps.common.runscript_harness import binary_harness


_VARIANT_DIRS: Mapping[str, Sequence[str]] = {
    LanguageCode.FR_FR: ("videos/stream/fr_france",),
    LanguageCode.AR_MA: ("videos/strem/ar_maroc", "videos/stream/ar_maroc"),
}

_RANDOM_SUFFIX = re.compile(r"(_|-)[A-Za-z0-9]{4,}(?:_[A-Za-z0-9]{2,})*$")
_NUMERIC_PREFIX = re.compile(r"^(?P<section>\d+)(?:\D+(?P<lecture>\d+))?")


@dataclass
class MatchResult:
    lang: str
    lecture: Lecture | None
    storage_path: str
    source: Path
    reason: str


def _coerce_argv(argv: Iterable[str] | None) -> List[str]:
    if argv is None:
        return []
    if isinstance(argv, (list, tuple)):
        items = list(argv)
    else:
        items = str(argv).split()
    coerced: List[str] = []
    for token in items:
        if token.startswith("--"):
            coerced.append(token)
            continue
        if "=" in token:
            key, value = token.split("=", 1)
            coerced.extend([f"--{key.replace('_', '-')}", value])
        else:
            coerced.append(token)
    return coerced


def _parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Attach language-specific video variants to lectures.")
    parser.add_argument("--course-slug", dest="course_slug", default=None, help="Restrict ingestion to a course slug")
    parser.add_argument("--media-root", dest="media_root", default=settings.MEDIA_ROOT, help="Media root base directory")
    parser.add_argument("--apply", dest="apply", action="store_true", help="Persist changes (default: dry-run)")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true", help="Force dry-run even if --apply")
    parser.add_argument("--verbose", dest="verbose", action="store_true", help="Verbose logging")
    coerced = _coerce_argv(argv)
    return parser.parse_args(coerced)


def _strip_random_suffix(stem: str) -> str:
    candidate = stem
    while True:
        match = _RANDOM_SUFFIX.search(candidate)
        if not match:
            break
        candidate = candidate[: match.start()]
    return candidate.rstrip("_- ")


def _normalize_stem(name: str) -> str:
    return slugify(_strip_random_suffix(name))


def _collect_files(media_root: Path) -> Dict[str, List[Path]]:
    results: Dict[str, List[Path]] = {code: [] for code in LanguageCode.values}
    for lang, subdirs in _VARIANT_DIRS.items():
        collected: List[Path] = []
        for relative in subdirs:
            base = (media_root / relative).resolve()
            if not base.exists() or not base.is_dir():
                continue
            collected.extend(sorted(p for p in base.rglob("*.mp4") if p.is_file()))
        results[lang] = collected
    return results


def _build_lecture_indexes(course: Course) -> Tuple[MutableMapping[str, Lecture], MutableMapping[str, Lecture]]:
    numeric_index: MutableMapping[str, Lecture] = {}
    slug_index: MutableMapping[str, Lecture] = {}

    lectures = (
        Lecture.objects.filter(course=course, is_published=True)
        .select_related("section")
        .order_by("section__order", "order")
    )

    for lecture in lectures:
        section_order = lecture.section.order
        lecture_order = lecture.order
        numeric_keys = {
            f"{section_order}-{lecture_order}",
            f"{section_order}_{lecture_order}",
            f"{section_order:02d}{lecture_order:02d}",
        }
        for key in numeric_keys:
            numeric_index.setdefault(key, lecture)

        title_slug = slugify(lecture.title or "")
        numeric_slug = slugify(f"{section_order}-{lecture_order}-{lecture.title}") if lecture.title else None
        if title_slug:
            slug_index.setdefault(title_slug, lecture)
        if numeric_slug:
            slug_index.setdefault(numeric_slug, lecture)
    return numeric_index, slug_index


def _match_file(
    relative_path: str,
    lang: str,
    numeric_index: Mapping[str, Lecture],
    slug_index: Mapping[str, Lecture],
) -> Tuple[Lecture | None, str]:
    stem = Path(relative_path).stem
    clean_stem = _strip_random_suffix(stem)

    numeric_match = _NUMERIC_PREFIX.match(clean_stem)
    if numeric_match:
        section = numeric_match.group("section")
        lecture = numeric_match.group("lecture")
        if section and lecture:
            for key in (f"{section}-{lecture}", f"{section}_{lecture}", f"{int(section):02d}{int(lecture):02d}"):
                if key in numeric_index:
                    return numeric_index[key], "numeric"
        if section and not lecture:
            for candidate_key in (f"{section}-1", f"{section}_1", f"{int(section):02d}01"):
                if candidate_key in numeric_index:
                    return numeric_index[candidate_key], "section-default"

    normalized = _normalize_stem(clean_stem)
    if normalized and normalized in slug_index:
        return slug_index[normalized], "slug"

    if numeric_match:
        section = numeric_match.group("section")
        lecture = numeric_match.group("lecture")
        if section and lecture:
            flattened = slugify(f"{section}-{lecture}")
            if flattened in slug_index:
                return slug_index[flattened], "numeric-slug"

    return None, "unmatched"


def _relativize(media_root: Path, absolute: Path) -> str:
    try:
        rel = absolute.relative_to(media_root)
    except ValueError:
        rel = absolute
    return str(rel).replace("\\", "/")


@binary_harness
@transaction.atomic
def run(*, script_args: Iterable[str] | None = None):
    args = _parse_args(script_args)
    media_root = Path(args.media_root).resolve()
    dry_run = args.dry_run or not args.apply

    if args.course_slug:
        courses = list(Course.objects.filter(slug=args.course_slug))
    else:
        courses = list(Course.objects.filter(is_published=True))

    if not courses:
        return {
            "ok": True,
            "name": "ingest_multilang_variants",
            "duration": 0.0,
            "logs": [f"No course matched slug={args.course_slug!r}"]
        }

    files_by_lang = _collect_files(media_root)
    matches: List[MatchResult] = []

    for course in courses:
        numeric_index, slug_index = _build_lecture_indexes(course)
        for lang, files in files_by_lang.items():
            for file_path in files:
                rel = _relativize(media_root, file_path)
                lecture, reason = _match_file(rel, lang, numeric_index, slug_index)
                matches.append(MatchResult(lang=lang, lecture=lecture, storage_path=rel, source=file_path, reason=reason))

    plan: List[Dict[str, object]] = []
    orphans: List[MatchResult] = []

    for match in matches:
        if match.lecture is None:
            orphans.append(match)
            continue

        variant = LectureVideoVariant.objects.filter(lecture=match.lecture, lang=match.lang).first()
        should_default = match.lang == LanguageCode.FR_FR

        if variant is None:
            action = "create"
        else:
            needs_update = False
            if variant.storage_path != match.storage_path:
                needs_update = True
            if variant.is_default != should_default:
                needs_update = True
            action = "update" if needs_update else "noop"

        plan.append(
            {
                "lecture_id": match.lecture.pk,
                "lecture_title": match.lecture.title,
                "lang": match.lang,
                "storage_path": match.storage_path,
                "should_default": should_default,
                "action": action,
                "variant_id": variant.pk if variant else None,
            }
        )

    counts = {"create": 0, "update": 0, "noop": 0}
    mode = "APPLY" if args.apply and not dry_run else "DRY-RUN"
    print(f"[{mode}] Variantes détectées: {len(plan)} (orphans={len(orphans)})")
    for item in plan:
        counts[item["action"]] += 1
        print(
            f" - {item['action'].upper():>6} | lecture #{item['lecture_id']} · {item['lang']} · {item['storage_path']}"
        )

    if orphans:
        print("[WARN] Fichiers orphelins:")
        for orphan in orphans:
            print(f"   - {orphan.lang} · {orphan.storage_path} (raison={orphan.reason})")

    if dry_run:
        transaction.set_rollback(True)
    else:
        for item in plan:
            action = item["action"]
            if action == "noop":
                continue
            if action == "create":
                LectureVideoVariant.objects.create(
                    lecture_id=item["lecture_id"],
                    lang=item["lang"],
                    storage_path=item["storage_path"],
                    is_default=item["should_default"],
                )
            elif action == "update":
                variant = LectureVideoVariant.objects.get(pk=item["variant_id"])
                variant.storage_path = item["storage_path"]
                variant.is_default = item["should_default"]
                variant.save(update_fields=["storage_path", "is_default", "updated_at"])

    summary = {
        "create": counts["create"],
        "update": counts["update"],
        "noop": counts["noop"],
        "orphans": len(orphans),
        "dry_run": dry_run,
    }

    return {
        "ok": True,
        "name": "ingest_multilang_variants",
        "duration": 0.0,
        "logs": [
            {
                "summary": summary,
                "plan": plan,
                "orphans": [
                    {"lang": item.lang, "path": item.storage_path, "reason": item.reason}
                    for item in orphans
                ],
            }
        ],
    }
