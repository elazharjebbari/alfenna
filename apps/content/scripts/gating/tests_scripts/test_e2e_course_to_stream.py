from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from apps.catalog.models.models import Course
from apps.content.models import Lecture
from apps.content.scripts import seed_stream_demo
from apps.common.runscript_harness import binary_harness


@binary_harness
def run(*args, **kwargs):
    print("== e2e_course_to_stream: start ==")

    seed_stream_demo.run()

    course = Course.objects.get(slug="stream-demo")
    free_lecture = (
        Lecture.objects.filter(course=course, is_free=True)
        .select_related("section")
        .order_by("section__order", "order")
        .first()
    )
    premium_lecture = (
        Lecture.objects.filter(course=course, is_free=False)
        .select_related("section")
        .order_by("section__order", "order")
        .first()
    )
    assert free_lecture and premium_lecture, "Seed should provide free and premium lectures"

    client = Client()

    # Page de la leçon gratuite
    free_url = reverse(
        "content:lecture-detail",
        kwargs={
            "course_slug": course.slug,
            "section_order": free_lecture.section.order,
            "lecture_order": free_lecture.order,
        },
    )
    page_resp = client.get(free_url)
    assert page_resp.status_code == 200, f"Free lecture page should be accessible, got {page_resp.status_code}"
    page_resp.render()
    context = getattr(page_resp, "context_data", None) or page_resp.context
    assert context, "LectureDetailView should render context"
    player_src = context.get("player_src")
    expected_src = reverse("learning:stream", args=[free_lecture.pk])
    assert player_src == expected_src, "LectureDetailView should expose stream URL"

    head_resp = client.head(player_src)
    assert head_resp.status_code == 206, "Stream HEAD must return 206"
    assert head_resp["Content-Range"].startswith("bytes 0-"), "Content-Range header missing"

    # Leçon premium anonyme → verrou
    premium_url = reverse(
        "content:lecture-detail",
        kwargs={
            "course_slug": course.slug,
            "section_order": premium_lecture.section.order,
            "lecture_order": premium_lecture.order,
        },
    )
    premium_resp = client.get(premium_url, follow=False)
    assert premium_resp.status_code in (302, 403), "Premium lecture should be gated for anonymous"

    # Staff preview
    staff, _ = User.objects.get_or_create(
        username="stream_staff",
        defaults={"is_staff": True, "is_superuser": True},
    )
    staff.set_password("demo")
    staff.save()

    assert client.login(username="stream_staff", password="demo")
    preview_resp = client.get(premium_url + "?preview=1")
    assert preview_resp.status_code == 200, "Staff preview should unlock premium page"

    stream_url = reverse("learning:stream", args=[premium_lecture.pk]) + "?preview=1"
    preview_head = client.head(stream_url)
    assert preview_head.status_code == 206, "Staff preview should allow stream HEAD"

    print("== e2e_course_to_stream: OK ✅ ==")
