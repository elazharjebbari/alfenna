from __future__ import annotations

import os
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalog.models.models import Course
from apps.content.models import Lecture, Section
from apps.learning.models import LectureComment, Progress


class Command(BaseCommand):
    help = "Reset learning data (course, sections, lectures, progress, comments) for CLI test runs."

    target_settings_module = "lumierelearning.settings.test_cli"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Allow execution outside the CLI test settings module",
        )
        parser.add_argument(
            "--course-slug",
            dest="course_slugs",
            action="append",
            default=[],
            help="Limit reset to the given course slug (can be provided multiple times)",
        )

    def handle(self, *args, **options):
        force = options.get("force", False)
        raw_slugs = options.get("course_slugs") or []
        course_slugs = sorted({slug.strip() for slug in raw_slugs if slug and slug.strip()})

        active_settings = os.environ.get("DJANGO_SETTINGS_MODULE") or ""
        expected_settings = self.target_settings_module

        if not force and active_settings != expected_settings:
            raise CommandError(
                "content_reset_learning is restricted to the CLI test settings module. "
                "Use --force to override if you know what you are doing."
            )

        courses_qs = Course.objects.all()
        if course_slugs:
            courses_qs = courses_qs.filter(slug__in=course_slugs)

        course_ids = list(courses_qs.values_list("id", flat=True))
        if not course_ids and course_slugs:
            self.stdout.write("No courses matched the provided slug(s); nothing to reset.")
            return

        with transaction.atomic():
            base_kwargs = {"lecture__course_id__in": course_ids} if course_ids else {}
            prog_qs = Progress.objects.filter(**base_kwargs)
            comment_qs = LectureComment.objects.filter(**base_kwargs)
            lecture_qs = Lecture.objects.filter(course_id__in=course_ids) if course_ids else Lecture.objects.all()
            section_qs = Section.objects.filter(course_id__in=course_ids) if course_ids else Section.objects.all()

            progress_count = prog_qs.count()
            comment_count = comment_qs.count()
            lecture_count = lecture_qs.count()
            section_count = section_qs.count()
            course_count = courses_qs.count()

            self.stdout.write(
                "Resetting learning data for "
                + (", ".join(course_slugs) if course_slugs else "all courses")
            )

            prog_qs.delete()
            comment_qs.delete()
            lecture_qs.delete()
            section_qs.delete()
            if course_ids or not course_slugs:
                courses_qs.delete()

        self.stdout.write(
            self.style.SUCCESS(
                "Learning data reset complete. "
                f"courses={course_count} sections={section_count} "
                f"lectures={lecture_count} progress={progress_count} comments={comment_count}"
            )
        )
