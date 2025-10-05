from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.atelier.compose.hydrators.learning.hydrators import _lecture_slug
from apps.catalog.models.models import Course
from apps.common.runscript_harness import binary_harness, skip
from apps.content.models import Lecture
from apps.billing.models import Entitlement


@binary_harness
def run(*args, **kwargs):
    course_slug = kwargs.get("course_slug") or "bougies-naturelles"
    try:
        course = Course.objects.get(slug=course_slug)
    except Course.DoesNotExist:
        return skip(f"course {course_slug} unavailable")

    lectures = list(
        Lecture.objects.filter(course=course, is_published=True)
        .select_related("section")
        .order_by("section__order", "order")
    )
    if not lectures:
        return skip("course has no lectures")

    free_lecture = next((lec for lec in lectures if lec.is_free), None)
    locked_lecture = next((lec for lec in lectures if not lec.is_free), None)
    if free_lecture is None:
        free_lecture = lectures[0]
    if locked_lecture is None:
        locked_lecture = lectures[-1]

    client = Client()
    demo_resp = client.get(reverse("pages:demo", kwargs={"course_slug": course.slug}))
    demo_html = demo_resp.content.decode()
    demo_ok = demo_resp.status_code == 200 and 'data-demo="1"' in demo_html and 'data-demo="0"' not in demo_html

    learn_url_locked = reverse(
        "pages:lecture-detail",
        kwargs={"course_slug": course.slug, "lecture_slug": _lecture_slug(locked_lecture)},
    )

    anon_resp = client.get(learn_url_locked)
    anon_redirect_ok = anon_resp.status_code in {301, 302} and "login" in (anon_resp.headers.get("Location", "") or "")

    User = get_user_model()
    user, created = User.objects.get_or_create(
        username="demo-smoke",
        defaults={"email": "demo@local"},
    )
    if created:
        user.set_password("passdemo123")
        user.save(update_fields=["password"])
    else:
        if not user.check_password("passdemo123"):
            user.set_password("passdemo123")
            user.save(update_fields=["password"])

    Entitlement.objects.filter(user=user, course=course).delete()

    assert client.login(username="demo-smoke", password="passdemo123")
    authed_resp = client.get(learn_url_locked)
    authed_html = authed_resp.content.decode()
    authed_locked = authed_resp.status_code == 200 and 'data-demo="0"' in authed_html

    if locked_lecture is None or locked_lecture.is_free:
        locked_blocked = True
        entitled_ok = True
    else:
        stream_url_locked = reverse("learning:stream", args=[locked_lecture.pk])
        locked_stream_resp = client.get(stream_url_locked, HTTP_RANGE="bytes=0-1")
        locked_blocked = locked_stream_resp.status_code in {301, 302, 401, 403, 404}

        Entitlement.objects.get_or_create(user=user, course=course)
        entitled_stream_resp = client.get(stream_url_locked, HTTP_RANGE="bytes=0-1")
        entitled_ok = entitled_stream_resp.status_code in {200, 206}

    free_ok = False
    if free_lecture:
        free_url = reverse(
            "pages:lecture-detail",
            kwargs={"course_slug": course.slug, "lecture_slug": _lecture_slug(free_lecture)},
        )
        free_resp = client.get(free_url)
        free_ok = free_resp.status_code == 200 and 'data-demo="1"' in free_resp.content.decode()

    overall = demo_ok and anon_redirect_ok and authed_locked and locked_blocked and entitled_ok and free_ok
    logs = [
        {
            "demo_status": demo_resp.status_code,
            "demo_unlocked": demo_ok,
            "anon_redirect": anon_redirect_ok,
            "authed_locked": authed_locked,
            "locked_blocked": locked_blocked,
            "entitled_unlocked": entitled_ok,
            "free_unlocked": free_ok,
        }
    ]
    return {
        "ok": overall,
        "name": "pages_smoke_demo_learn",
        "duration": 0.0,
        "logs": logs,
    }
