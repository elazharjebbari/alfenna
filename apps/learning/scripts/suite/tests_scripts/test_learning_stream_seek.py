# apps/learning/scripts/learning_stream_seek.py
from __future__ import annotations
import os
from typing import List

from django.core.files.storage import default_storage
from django.test import Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from apps.content.models import Lecture
from apps.learning.views import _storage_path_and_size
from apps.billing.models import Entitlement
from apps.common.runscript_harness import binary_harness


def _print(msg: str): print(msg, flush=True)

def _iter_mp4(prefix: str) -> List[str]:
    out: List[str] = []
    def _walk(p: str):
        try:
            dirs, files = default_storage.listdir(p)
        except Exception:
            return
        for f in files:
            if f.lower().endswith(".mp4"):
                out.append(f"{p.rstrip('/')}/{f}")
        for d in dirs:
            _walk(f"{p.rstrip('/')}/{d}")
    _walk(prefix.rstrip("/"))
    return sorted(set(out))

def _pick_streamable_lecture() -> Lecture:
    qs = (Lecture.objects
          .select_related("section", "course")
          .filter(is_published=True, course__is_published=True)
          .order_by("course_id", "section__order", "order"))
    # 1) essaye une leçon déjà streamable
    for lec in qs:
        try:
            _storage_path_and_size(lec)
            return lec
        except Exception:
            continue
    # 2) sinon, lie un .mp4 au premier candidat
    lec = qs.first()
    assert lec, "Aucune leçon publiée — seed ton catalogue."
    files = _iter_mp4("videos/learning")
    assert files, "Aucun .mp4 sous media/videos/learning — place des fichiers avant ce test."
    # on privilégie video_path si dispo, sinon video_file.name
    if hasattr(lec, "video_path"):
        lec.video_path = files[0]
        lec.save(update_fields=["video_path"])
    else:
        lec.video_file.name = files[0]
        lec.save(update_fields=["video_file"])
    return lec

def _ensure_entitlement(user, course):
    Entitlement.objects.get_or_create(user=user, course=course)

@binary_harness
def run(*args):
    print("== learning_stream_seek: start ==")
    lec = _pick_streamable_lecture()
    course = lec.course
    _print(f"[pick] lecture pk={lec.pk} course={course.id} '{course.title}' s{lec.section.order}/l{lec.order}")

    User = get_user_model()
    u, _ = User.objects.get_or_create(username="stream_tester", defaults={"email": "s@ex.com"})
    u.set_password("p@ss1234"); u.save()
    _ensure_entitlement(u, course)

    c = Client()
    assert c.login(username="stream_tester", password="p@ss1234")
    url = reverse("learning:stream", args=[lec.id])

    # HEAD (200 ou 206 selon Range implicite)
    r = c.head(url)
    assert r.status_code in (200, 206), f"HEAD bad status {r.status_code}"
    assert r["Accept-Ranges"] == "bytes", "Accept-Ranges manquant"

    # GET avec Range
    r = c.get(url, HTTP_RANGE="bytes=10000-20000")
    assert r.status_code == 206, f"GET range bad status {r.status_code}"
    assert "Content-Range" in r, "Content-Range manquant"
    # 20000 - 10000 + 1 = 10001
    expect_len = 20001 - 10000
    assert int(r["Content-Length"]) == expect_len, f"Content-Length attendu {expect_len}, got {r['Content-Length']}"

    print("== learning_stream_seek: OK ✅ ==")
