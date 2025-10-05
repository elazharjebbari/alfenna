from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.common.runscript_harness import binary_harness
from apps.content.models import Lecture, LectureVideoVariant, LanguageCode
from apps.content.scripts import seed_stream_demo


@binary_harness
def run():  # pragma: no cover
    seed_stream_demo.run()

    lecture = (
        Lecture.objects.select_related("section", "course")
        .filter(course__slug="stream-demo", section__order=1, order=1)
        .first()
    )
    assert lecture, "seed_stream_demo must create the first lecture"

    LectureVideoVariant.objects.update_or_create(
        lecture=lecture,
        lang=LanguageCode.FR_FR,
        defaults={
            "storage_path": "videos/stream/fr_france/stream_demo_fr.mp4",
            "is_default": True,
        },
    )
    LectureVideoVariant.objects.update_or_create(
        lecture=lecture,
        lang=LanguageCode.AR_MA,
        defaults={
            "storage_path": "videos/strem/ar_maroc/stream_demo_ar.mp4",
            "is_default": False,
        },
    )

    User = get_user_model()
    user, _ = User.objects.get_or_create(username="multilang-smoke", defaults={"email": "multi@example.com"})
    user.set_password("pass1234!")
    user.save(update_fields=["password"])

    client = Client()
    assert client.login(username="multilang-smoke", password="pass1234!"), "Login must succeed"

    slug = f"s{lecture.section.order}-l{lecture.order}"
    url = reverse("pages:lecture-detail", kwargs={"course_slug": lecture.course.slug, "lecture_slug": slug})
    response = client.get(url, {"lang": LanguageCode.AR_MA})

    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    body = response.content.decode("utf-8", errors="ignore")
    assert "?lang=ar_MA" in body, "Stream URL should include lang query param"

    return {"ok": True, "name": "test_learn_multilang_smoke", "duration": 0.0, "logs": []}
