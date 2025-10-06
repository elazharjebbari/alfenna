"""If no media source exists the frontend must not trigger stream calls."""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.billing.models import Entitlement
from apps.catalog.models.models import Course
from apps.common.runscript_harness import binary_harness
from apps.content.models import Lecture
from apps.content.scripts import attach_demo_media, seed_stream_demo
from .test_attach_demo_media_idempotent import _ensure_gating_course, _clear_video_fields


@binary_harness
def run(*args, **kwargs):
    seed_stream_demo.run()
    attach_demo_media.run()

    course = _ensure_gating_course()
    _clear_video_fields(course)

    # Ensure all lectures truly have no usable source.
    Lecture.objects.filter(course=course).update(video_url="", video_path="", video_file=None)

    User = get_user_model()
    user, _ = User.objects.get_or_create(username="buyer_lock", defaults={"email": "buyer_lock@example.com"})
    user.set_password("demo")
    user.save()

    Entitlement.objects.get_or_create(user=user, course=course)

    client = Client()
    assert client.login(username="buyer_lock", password="demo"), "Login failed"

    session = client.session
    entitled = set(str(cid) for cid in session.get("entitled_course_ids", []))
    entitled.add(str(course.id))
    session["entitled_course_ids"] = list(entitled)
    session.save()

    path = reverse("pages:lecture", kwargs={"course_slug": course.slug})
    resp = client.get(path)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"

    html = resp.content.decode("utf-8")
    assert 'data-reason="no-source"' in html, "Lecture wrapper must expose no-source reason"
    assert 'data-locked="1"' in html, "Lecture should be flagged locked when source missing"
    assert "/learning/stream/" not in html, "Template must not inject stream endpoint when no source"
    assert 'data-src="' not in html, "Video tag should not render data-src without source"

    # Restore demo attachments for subsequent tests.
    attach_demo_media.run()

    return {
        "ok": True,
        "name": "test_no_source_no_network_call",
        "duration": 0.0,
        "logs": ["no source path rendered without stream url"],
    }

