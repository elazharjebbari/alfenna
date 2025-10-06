import os

from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from apps.catalog.models.models import Course
from apps.content.models import Lecture
from apps.content.scripts import seed_stream_demo
from apps.common.runscript_harness import binary_harness
from apps.billing.models import Entitlement


@binary_harness
def run(*args, **kwargs):
    print("== stream_range: start ==")

    seed_stream_demo.run()

    course = Course.objects.get(slug="stream-demo")
    free_lecture = (
        Lecture.objects.filter(course=course, is_free=True)
        .order_by("section__order", "order")
        .first()
    )
    premium_lecture = (
        Lecture.objects.filter(course=course, is_free=False)
        .order_by("section__order", "order")
        .first()
    )
    assert free_lecture and premium_lecture, "Seed must provide free and premium lectures"

    client = Client()
    free_url = reverse("learning:stream", args=[free_lecture.pk])

    # HEAD sur free → 206 + headers.
    head_resp = client.head(free_url)
    assert head_resp.status_code == 206, f"HEAD free lecture should return 206, got {head_resp.status_code}"
    assert head_resp["Accept-Ranges"] == "bytes"
    assert head_resp["Content-Length"].isdigit()
    assert head_resp["Content-Range"].startswith("bytes 0-")

    # GET avec Range partiel.
    partial_resp = client.get(free_url, HTTP_RANGE="bytes=0-1023")
    assert partial_resp.status_code == 206, f"Partial range should return 206, got {partial_resp.status_code}"
    assert partial_resp["Content-Range"].startswith("bytes 0-")
    body = b"".join(partial_resp.streaming_content)
    expected_length = min(1024, os.path.getsize(free_lecture.video_path))
    assert len(body) == expected_length, "Returned payload length must match range"

    # Premium anonyme → redirection ou 403, jamais video payload.
    premium_url = reverse("learning:stream", args=[premium_lecture.pk])
    blocked_resp = client.get(premium_url, HTTP_RANGE="bytes=0-128")
    assert blocked_resp.status_code in (302, 403), f"Premium anon should be blocked, got {blocked_resp.status_code}"

    # Auth utilisateur avec entitlement session.
    user, _ = User.objects.get_or_create(username="stream_buyer")
    user.set_password("demo")
    user.save()

    Entitlement.objects.get_or_create(user=user, course=course)

    auth_client = Client()
    assert auth_client.login(username="stream_buyer", password="demo")
    session = auth_client.session
    entitled = set(session.get("entitled_course_ids", []))
    entitled.add(course.id)
    session["entitled_course_ids"] = list(entitled)
    session.save()

    entitled_resp = auth_client.get(premium_url, HTTP_RANGE="bytes=0-512")
    assert entitled_resp.status_code == 206, f"Entitled user should access premium, got {entitled_resp.status_code}"
    assert entitled_resp["Content-Range"].startswith("bytes 0-")
    payload = b"".join(entitled_resp.streaming_content)
    premium_size = os.path.getsize(premium_lecture.video_path)
    assert len(payload) == min(513, premium_size), "Content length mismatch for premium range"

    print("== stream_range: OK ✅ ==")
