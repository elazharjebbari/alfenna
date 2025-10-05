# apps/content/scripts/gating_perf_guard.py
from django.test import Client
from django.urls import reverse
from django.db import connection
from django.test.utils import CaptureQueriesContext
from apps.catalog.models.models import Course
from apps.content.models import Section, Lecture
from apps.common.runscript_harness import binary_harness

MAX_Q = 12

@binary_harness
def run(*args):
    print('== gating_perf_guard: start ==')
    c = Client()

    course = Course.objects.filter(is_published=True).first()
    assert course, 'Aucun cours publié. Seed un cours.'

    # Chercher une leçon censée être premium (au-delà du free N)
    free_n = int(course.free_lectures_count or 0)
    # naïf: prendre la dernière
    sec = course.sections.order_by('order').last()
    lec = sec.lectures.order_by('order').last()

    url = reverse('content:lecture', kwargs={'course_slug': course.slug, 'section_order': sec.order, 'lecture_order': lec.order})

    with CaptureQueriesContext(connection) as ctx:
        r = c.get(url, follow=False)
    assert r.status_code in (302, 403), f"Expected lock on premium lecture, got {r.status_code}"
    assert len(ctx) <= MAX_Q, f"Trop de requêtes ({len(ctx)}) pour un refus d'accès"

    print('== gating_perf_guard: OK ✅ ==')