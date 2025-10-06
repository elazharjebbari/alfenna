from __future__ import annotations

import argparse
from pathlib import Path
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from django.utils.text import slugify

from apps.catalog.models.models import Course
from apps.content.models import Lecture, LectureType, Section
from apps.learning.models import Progress
from apps.billing.models import Entitlement
from apps.content.scripts import seed_from_videos as seed_helpers
from apps.common.runscript_harness import binary_harness

SECTION_INFO = {
    1: (1, "Introduction"),
    2: (2, "Théorie — Matières premières"),
    3: (3, "Théorie — Matériel"),
    4: (4, "Théorie — Mèches"),
    5: (5, "Théorie — Parfums & Colorants"),
    6: (6, "Formules"),
    7: (7, "Pratiques"),
    8: (8, "Bonus"),
}

DEMO_LIMIT = 3
COURSE_SLUG = "bougies-naturelles"

@dataclass
class VideoItem:
    path: Path
    section_key: int
    title: str


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Reset and load Bougies Naturalles course from flat videos folder")
    parser.add_argument("--media-root", default=settings.MEDIA_ROOT, help="Base media root (default settings.MEDIA_ROOT)")
    parser.add_argument("--apply", action="store_true", help="Persist changes")
    parser.add_argument("--dry-run", action="store_true", help="Dry run")
    return parser.parse_args(list(argv) if argv is not None else [])


def list_top_level_videos(videos_dir: Path) -> list[Path]:
    return sorted([p for p in videos_dir.iterdir() if p.is_file() and p.suffix.lower() == ".mp4"], key=lambda p: p.name.lower())


def section_for_filename(stem: str) -> int:
    upper = stem.upper()
    if upper.startswith("BONUS"):
        return 8
    digits = ""
    for char in stem:
        if char.isdigit():
            digits += char
        else:
            break
    if digits:
        num = int(digits)
    else:
        return 7
    if num <= 6:
        return num
    if 7 <= num <= 14:
        return 7
    return 7


def clean_title(stem: str) -> str:
    trimmed = stem
    while trimmed and trimmed[0].isdigit():
        trimmed = trimmed[1:]
    trimmed = trimmed.lstrip("-_ ")
    title = trimmed.replace("_", " ").replace("-", " ")
    title = " ".join(title.split())
    return title.capitalize() or stem


def select_unique(files: list[Path]) -> list[Path]:
    grouped: dict[str, list[Path]] = {}
    for file in files:
        key = seed_helpers._normalize_group_key(file.stem)
        grouped.setdefault(key, []).append(file)
    selected: list[Path] = []
    for key, options in grouped.items():
        if not options:
            continue
        options = sorted(options, key=lambda p: p.name.lower())
        pick = next((p for p in options if seed_helpers._normalize_group_key(p.stem) == key and p.stem.lower() == key), None)
        if pick is None:
            pick = max(options, key=lambda p: p.stat().st_size if p.exists() else 0)
        selected.append(pick)
    return sorted(selected, key=lambda p: p.name.lower())


def build_items(files: list[Path]) -> list[VideoItem]:
    items: list[VideoItem] = []
    for file in files:
        section_key = section_for_filename(file.stem)
        title = clean_title(file.stem)
        items.append(VideoItem(path=file, section_key=section_key, title=title))
    items.sort(key=lambda item: (SECTION_INFO[item.section_key][0], item.path.name.lower()))
    return items


@binary_harness
def run(*args, **kwargs):
    opts = parse_args(kwargs.get("script_args"))
    dry_run = not opts.apply or opts.dry_run

    media_root = Path(opts.media_root).resolve()
    videos_dir = media_root / "videos"
    if not videos_dir.exists():
        raise SystemExit(f"videos directory not found: {videos_dir}")

    raw_files = list_top_level_videos(videos_dir)
    unique_files = select_unique(raw_files)
    items = build_items(unique_files)

    if not items:
        raise SystemExit("No MP4 files to ingest")

    info = {
        "course": COURSE_SLUG,
        "files": [str(it.path) for it in items],
        "dry_run": dry_run,
    }

    if dry_run:
        return {"ok": True, "name": "reset_and_load_bougies", "duration": 0.0, "logs": [info]}

    with transaction.atomic():
        course, _ = Course.objects.update_or_create(
            slug=COURSE_SLUG,
            defaults={
                "title": "Bougies naturelles — Atelier complet",
                "description": "Formation complète sur la fabrication artisanale de bougies naturelles.",
                "is_published": True,
            },
        )

        Progress.objects.filter(lecture__course=course).delete()
        Entitlement.objects.filter(course=course).delete()
        Lecture.objects.filter(course=course).delete()
        Section.objects.filter(course=course).delete()

        sections_cache: dict[int, Section] = {}
        # ensure deterministic order
        for section_key in [sec for sec in SECTION_INFO if any(item.section_key == sec for item in items)]:
            order, title = SECTION_INFO[section_key]
            section = Section.objects.create(
                course=course,
                title=title,
                order=order,
                is_published=True,
            )
            sections_cache[section_key] = section

        demo_counter = 0
        lecture_orders: dict[int, int] = {key: 0 for key in sections_cache}
        for item in items:
            section = sections_cache[item.section_key]
            lecture_orders[item.section_key] += 1
            is_demo = demo_counter < DEMO_LIMIT
            demo_counter += 1 if is_demo else 0
            Lecture.objects.create(
                course=course,
                section=section,
                title=item.title,
                order=lecture_orders[item.section_key],
                type=LectureType.VIDEO,
                video_path=f"videos/{item.path.name}",
                is_published=True,
                is_free=is_demo,
                is_demo=is_demo,
            )

        course.refresh_from_db()
        free_count = Lecture.objects.filter(course=course, is_demo=True).count()
        Course.objects.filter(pk=course.pk).update(free_lectures_count=free_count)

    info.update({"created": len(items), "demo": min(free_count, DEMO_LIMIT)})
    return {"ok": True, "name": "reset_and_load_bougies", "duration": 0.0, "logs": [info]}
