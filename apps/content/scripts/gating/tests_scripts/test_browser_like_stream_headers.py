"""Browser-like GET to stream endpoint should return proper range headers."""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.billing.models import Entitlement
from apps.catalog.models.models import Course
from apps.common.runscript_harness import binary_harness
from apps.content.models import Lecture
from apps.content.scripts import attach_demo_media, seed_stream_demo


@binary_harness
def run(*args, **kwargs):
    seed_stream_demo.run()
    attach_demo_media.run()

    course = Course.objects.get(slug="stream-demo")
    lecture = (
        Lecture.objects.filter(course=course, is_free=False)
        .order_by("section__order", "order")
        .first()
    )
    assert lecture, "Need a premium lecture to test streaming"

    User = get_user_model()
    user, _ = User.objects.get_or_create(username="buyer_browser", defaults={"email": "buyer_browser@example.com"})
    user.set_password("demo")
    user.save()

    Entitlement.objects.get_or_create(user=user, course=course)

    client = Client()
    assert client.login(username="buyer_browser", password="demo"), "Login failed"

    session = client.session
    entitled = set(str(cid) for cid in session.get("entitled_course_ids", []))
    entitled.add(str(course.id))
    session["entitled_course_ids"] = list(entitled)
    session.save()

    stream_url = reverse("learning:stream", args=[lecture.pk])
    resp = client.get(stream_url, HTTP_RANGE="bytes=0-")

    assert resp.status_code == 206, f"Expected 206 partial content, got {resp.status_code}"
    assert resp["Accept-Ranges"] == "bytes", "Accept-Ranges must be bytes"
    assert resp["Content-Range"].startswith("bytes 0-"), "Content-Range should start with bytes 0-"
    assert resp["Content-Type"].startswith("video/"), f"Unexpected MIME {resp['Content-Type']}"

    payload = b"".join(resp.streaming_content)
    assert payload, "Streamed payload should not be empty"

    return {
        "ok": True,
        "name": "test_browser_like_stream_headers",
        "duration": 0.0,
        "logs": [
            f"status={resp.status_code}",
            f"headers={{'Content-Type': '{resp['Content-Type']}', 'Content-Range': '{resp['Content-Range']}'}}",
        ],
    }

