from __future__ import annotations

from django.test import Client
from django.urls import reverse

from apps.common.runscript_harness import binary_harness, skip
from apps.content.models import Lecture


@binary_harness
def run(*args, **kwargs):
    lecture = (
        Lecture.objects.filter(is_published=True, is_free=True)
        .order_by("section__order", "order")
        .first()
    )
    if lecture is None:
        return skip("no free lecture available")

    client = Client()
    url = reverse("learning:stream", args=[lecture.pk])

    head_resp = client.head(url, HTTP_RANGE="bytes=0-1023")
    get_resp = client.get(url, HTTP_RANGE="bytes=0-2047")

    ok = (
        head_resp.status_code in {200, 206}
        and get_resp.status_code == 206
        and "Content-Range" in get_resp.headers
        and get_resp.headers["Content-Range"].startswith("bytes ")
    )

    logs = [
        {
            "lecture_id": lecture.pk,
            "head_status": head_resp.status_code,
            "get_status": get_resp.status_code,
            "content_range": get_resp.headers.get("Content-Range"),
        }
    ]

    return {"ok": ok, "name": "stream_headers_check", "duration": 0.0, "logs": logs}
