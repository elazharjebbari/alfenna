from pathlib import Path

from apps.catalog.models.models import Course
from apps.content.models import Lecture, LectureType
from apps.content.scripts import seed_stream_demo
from apps.common.runscript_harness import binary_harness


EXPECTED_STRUCTURE = [
    (1, 1, True),
    (1, 2, True),
    (2, 1, False),
    (2, 2, False),
]


@binary_harness
def run(*args, **kwargs):
    print("== seed_stream_demo: start ==")

    seed_stream_demo.run()

    course = Course.objects.get(slug="stream-demo")
    assert course.is_published, "Course stream-demo should be published"
    assert course.free_lectures_count == 2, "Course free_lectures_count must be 2"
    assert course.difficulty == "beginner", "Course difficulty should be beginner"

    sections = list(course.sections.order_by("order"))
    assert len(sections) == 2, "Course must have 2 sections"

    lectures = list(
        Lecture.objects.filter(course=course)
        .select_related("section")
        .order_by("section__order", "order")
    )
    assert len(lectures) == 4, "Course must have 4 lectures"

    seen_keys = set()
    lecture_ids = {lec.pk for lec in lectures}
    for lec, expected in zip(lectures, EXPECTED_STRUCTURE):
        section_order, lecture_order, is_free_expected = expected
        key = (lec.section.order, lec.order)
        assert key == (section_order, lecture_order), f"Unexpected lecture ordering: {key}"
        seen_keys.add(key)
        assert lec.type == LectureType.VIDEO, "Lecture must be a video"
        assert lec.is_published, "Lecture must be published"
        assert lec.is_free is is_free_expected, f"Lecture {key} free flag mismatch"
        assert lec.video_path, "Lecture video_path must be set"
        assert Path(lec.video_path).exists(), f"Video file missing for lecture {key}"

    assert seen_keys == {tuple(x[:2]) for x in EXPECTED_STRUCTURE}, "Missing lectures in structure"

    # Idempotence: relancer le seed et vérifier qu'on ne crée pas de doublons.
    seed_stream_demo.run()

    course.refresh_from_db()
    assert course.free_lectures_count == 2, "free_lectures_count should remain 2"

    lectures_after = list(
        Lecture.objects.filter(course=course)
        .select_related("section")
        .order_by("section__order", "order")
    )
    assert len(lectures_after) == 4, "Seed must stay idempotent on lecture count"
    assert {lec.pk for lec in lectures_after} == lecture_ids, "Seed should not duplicate lectures"

    for lec in lectures_after:
        assert lec.video_path, "Lecture video_path should persist after reseed"
        assert Path(lec.video_path).exists(), "Reseed must not delete video files"

    print("== seed_stream_demo: OK ✅ ==")
