"""Seed learning content from local MP4 files."""
from __future__ import annotations

import argparse
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from django.conf import settings
from django.db import transaction

from apps.catalog.models.models import Course
from apps.content.models import Lecture, LectureType, Section
from apps.common.runscript_harness import binary_harness


SECTION_TITLES = {
    1: "Bases",
    2: "Pratiques",
    3: "Défauts",
    4: "Moules",
    5: "Bonus",
}


@dataclass
class VideoEntry:
    source_path: Path
    section_order: int
    lecture_order: int
    title: str


def _parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed a demo course from MP4 files.")
    parser.add_argument("--media-root", dest="media_root", default=settings.MEDIA_ROOT, help="Media root (default: settings.MEDIA_ROOT)")
    parser.add_argument(
        "--source",
        dest="source",
        default="videos",
        help="Folder containing .mp4 files (absolute or relative to MEDIA_ROOT)",
    )
    parser.add_argument("--course-slug", dest="course_slug", default="bougies-naturelles", help="Slug of the course to upsert")
    parser.add_argument("--course-title", dest="course_title", default="Bougies naturelles — Atelier complet", help="Course title")
    parser.add_argument("--publish", dest="publish", action="store_true", help="Mark course as published")
    parser.add_argument("--apply", dest="apply", action="store_true", help="Persist changes (default: dry-run)")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true", help="Force dry-run even if --apply is set")
    if argv is None:
        args_list: List[str] = []
    elif isinstance(argv, (list, tuple)):
        args_list = list(argv)
    else:
        args_list = str(argv).split()
    return parser.parse_args(args_list)


_cleanup_re = re.compile(r"(?:\s|[_-])?(?:copy|final|draft|master|export|v\d+)(?:\s|[_-])*$")
_dup_suffix_re = re.compile(r"(?:\s|[_-])?\(\d+\)$")
_hash_suffix_re = re.compile(r"([_-])([A-Za-z0-9]{4,})$")


def _strip_hash_suffix(raw: str) -> str:
    candidate = raw
    while candidate:
        match = _hash_suffix_re.search(candidate)
        if not match:
            break
        token = match.group(2)
        if not any(ch.isdigit() or ch.isupper() for ch in token):
            break
        candidate = candidate[: match.start()]
    return candidate.rstrip("_- ")


def _normalize_group_key(stem: str) -> str:
    cleaned = _strip_hash_suffix(stem)
    base = cleaned.lower()
    changed = True
    while changed and base:
        changed = False
        new = _cleanup_re.sub("", base)
        if new != base:
            base = new
            changed = True
            continue
        new = _dup_suffix_re.sub("", base)
        if new != base:
            base = new
            changed = True
    base = base.rstrip(" _-")
    return base or stem.lower()


def _pick_files(source_dir: Path) -> List[Path]:
    files = sorted(p for p in source_dir.rglob("*.mp4") if p.is_file())
    grouped: Dict[str, List[Path]] = {}
    for file_path in files:
        key = _normalize_group_key(file_path.stem)
        grouped.setdefault(key, []).append(file_path)

    selected: List[Path] = []
    for key, candidates in grouped.items():
        if not candidates:
            continue
        exact = next((p for p in candidates if _normalize_group_key(p.stem) == key and p.stem.lower() == key), None)
        if exact:
            selected.append(exact)
            continue
        largest = max(candidates, key=lambda p: p.stat().st_size)
        selected.append(largest)
    return sorted(selected)


def _parse_orders(stem: str) -> Tuple[int, int]:
    raw = stem.replace(" ", "_")
    section_order = 99
    lecture_order = 99
    token = ""
    for ch in raw:
        if ch.isdigit():
            token += ch
        else:
            if token:
                if section_order == 99:
                    section_order = int(token)
                elif lecture_order == 99:
                    lecture_order = int(token)
                token = ""
            if ch in {"_", "-", "."}:
                break
    if section_order == 99 and token:
        section_order = int(token)
        token = ""
    if lecture_order == 99 and token:
        lecture_order = int(token)
    if section_order == 99:
        section_order = 1
    normalized_section = section_order if section_order in SECTION_TITLES else 5
    return normalized_section, lecture_order


def _human_title(stem: str) -> str:
    name = stem
    while name and name[0].isdigit():
        name = name[1:]
    name = name.lstrip("-_. ")
    name = name.replace("_", " ")
    name = name.replace("-", " ")
    if not name:
        return "Leçon"
    return name.capitalize()


def _build_entries(selected_files: List[Path]) -> List[VideoEntry]:
    entries: List[VideoEntry] = []
    per_section_counter: Dict[int, int] = {}
    for path in selected_files:
        section_order, lecture_order = _parse_orders(path.stem)
        if lecture_order == 99:
            lecture_order = per_section_counter.get(section_order, 0) + 1
        per_section_counter[section_order] = max(per_section_counter.get(section_order, 0), lecture_order)
        entries.append(
            VideoEntry(
                source_path=path,
                section_order=section_order,
                lecture_order=lecture_order,
                title=_human_title(path.stem),
            )
        )
    entries.sort(key=lambda e: (e.section_order, e.lecture_order, e.source_path.name))
    return entries


def _relative_video_path(media_root: Path, file_path: Path) -> str:
    try:
        rel = file_path.relative_to(media_root)
    except ValueError:
        rel = file_path
    return str(rel).replace(os.sep, "/")


def _resolve_source_dir(media_root: Path, source: str) -> Path:
    """Return a directory containing videos, ensuring it lives under MEDIA_ROOT."""

    candidates = []
    source_path = Path(source or "")
    if not source_path.is_absolute():
        parts = [part for part in source_path.parts if part not in {"."}]
        if parts and parts[0] == "media":
            parts = parts[1:]
        source_path = Path(*parts) if parts else Path(".")

    if source_path.is_absolute():
        candidates.append(source_path)
    else:
        candidates.append(Path.cwd() / source_path)
        candidates.append(media_root / source_path)

    resolved_media_root = media_root.resolve()
    seen: set[Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except FileNotFoundError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        if not resolved.exists():
            continue
        try:
            resolved.relative_to(resolved_media_root)
        except ValueError:
            continue
        if resolved.is_dir():
            return resolved

    raise SystemExit(
        f"Source directory not found under MEDIA_ROOT: {source} (searched: {', '.join(str(c) for c in candidates)})"
    )


@binary_harness
def run(*args, **kwargs):
    opts = _parse_args(kwargs.get("script_args"))
    dry_run = not opts.apply or opts.dry_run

    media_root = Path(opts.media_root).resolve()
    source_dir = _resolve_source_dir(media_root, opts.source)

    selected_files = _pick_files(source_dir)
    if not selected_files:
        raise SystemExit("No MP4 files found in source directory")

    entries = _build_entries(selected_files)

    info = {
        "files": [str(e.source_path) for e in entries],
        "dry_run": dry_run,
    }

    if dry_run:
        return {"ok": True, "name": "seed_from_videos", "duration": 0.0, "logs": ["dry-run", info]}

    course_defaults = {
        "title": opts.course_title,
        "description": "Atelier complet sur la fabrication artisanale de bougies naturelles.",
        "difficulty": "beginner",
        "free_lectures_count": 0,
        "is_published": bool(opts.publish),
    }

    with transaction.atomic():
        course, _ = Course.objects.update_or_create(
            slug=opts.course_slug,
            defaults=course_defaults,
        )

        sections: Dict[int, Section] = {}
        for section_order in sorted({e.section_order for e in entries}):
            title = SECTION_TITLES.get(section_order, SECTION_TITLES[5])
            section, _ = Section.objects.update_or_create(
                course=course,
                order=section_order,
                defaults={"title": title, "is_published": True},
            )
            sections[section_order] = section

        Section.objects.filter(course=course).exclude(order__in=sections.keys()).delete()

        Lecture.objects.filter(course=course).exclude(
            section__order__in=sections.keys()
        ).delete()

        total_free = 0
        free_cutoff = 3
        keep_pairs: Dict[int, List[int]] = {order: [] for order in sections.keys()}
        for idx, entry in enumerate(entries, start=1):
            section = sections[entry.section_order]
            video_rel_path = _relative_video_path(media_root, entry.source_path)
            is_free = idx <= free_cutoff
            is_demo = is_free
            defaults = {
                "course": course,
                "title": entry.title,
                "type": LectureType.VIDEO,
                "is_published": True,
                "is_free": is_free,
                "is_demo": is_demo,
                "video_path": video_rel_path,
                "video_file": None,
            }
            Lecture.objects.update_or_create(
                section=section,
                order=entry.lecture_order,
                defaults=defaults,
            )
            keep_pairs.setdefault(entry.section_order, []).append(entry.lecture_order)
            if is_free:
                total_free += 1

        for section_order, section in sections.items():
            Lecture.objects.filter(section=section).exclude(order__in=keep_pairs.get(section_order, [])).delete()

        Course.objects.filter(pk=course.pk).update(free_lectures_count=total_free)

    info.update({"course": opts.course_slug, "free": total_free, "count": len(entries)})
    return {"ok": True, "name": "seed_from_videos", "duration": 0.0, "logs": [info]}
