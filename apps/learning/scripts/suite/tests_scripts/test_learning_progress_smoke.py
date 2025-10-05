# apps/learning/scripts/learning_progress_smoke.py
from __future__ import annotations
import time

from django.test import Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.cache import cache

from apps.content.models import Lecture
from apps.learning.models import Progress
from apps.billing.models import Entitlement
from apps.learning.views import PROGRESS_THROTTLE_SECONDS
from apps.common.runscript_harness import binary_harness


def _ensure_entitlement(user, course):
    Entitlement.objects.get_or_create(user=user, course=course)


@binary_harness
def run(*args):
    print("== learning_progress_smoke: start ==")

    # 1) Choisir une leçon publiée
    lec = (
        Lecture.objects
        .select_related("section", "course")
        .filter(section__course__is_published=True, is_published=True)
        .first()
    )
    assert lec, "Aucune lecture publiée"
    course = lec.course

    # 2) User + entitlement pour bypass le gating
    User = get_user_model()
    u, _ = User.objects.get_or_create(username="progress_tester", defaults={"email": "p@ex.com"})
    u.set_password("p@ss1234"); u.save()
    _ensure_entitlement(u, course)

    # 3) Login et URL
    c = Client()
    assert c.login(username="progress_tester", password="p@ss1234")
    url = reverse("learning:progress", args=[lec.id])

    # 4) Premier POST: position
    r = c.post(url, {"position_ms": "12345"})
    assert r.status_code == 200, f"POST position bad status {r.status_code}"
    data = r.json() if hasattr(r, "json") else {}
    assert not data.get("throttled"), f"Premier POST throttled: {data}"
    p = Progress.objects.get(user=u, lecture=lec)
    assert p.last_position_ms == 12345, f"position non persistée ({p.last_position_ms})"

    # 5) Attendre au-delà du throttle (ou purger la clé)
    #    → version 'attente'
    time.sleep(PROGRESS_THROTTLE_SECONDS + 0.5)

    #    → alternative 'purge' si tu préfères (décommente):
    # cache.delete(f"learning:progress_throttle:{u.id}:{lec.id}")

    # 6) Second POST: completed
    r = c.post(url, {"completed": "1"})
    assert r.status_code == 200, f"POST completed bad status {r.status_code}"
    data = r.json() if hasattr(r, "json") else {}
    assert not data.get("throttled"), f"Second POST throttled: {data}"

    p.refresh_from_db()
    assert p.is_completed is True, "flag completed non persisté"
    print("== learning_progress_smoke: OK ✅ ==")
