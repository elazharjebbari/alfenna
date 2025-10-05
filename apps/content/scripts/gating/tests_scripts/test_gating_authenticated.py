# apps/content/scripts/gating_authenticated.py
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from apps.catalog.models.models import Course
from apps.content.models import Section, Lecture
from apps.common.runscript_harness import binary_harness

@binary_harness
def run(*args):
    print('== gating_authenticated: start ==')

    course = Course.objects.filter(is_published=True).first()
    assert course, 'Aucun cours publié. Seed un cours.'

    # Prendre une leçon au-delà du quota free
    sec = course.sections.order_by('order').last()
    lec = sec.lectures.order_by('order').last()

    u, _ = User.objects.get_or_create(username='buyer')
    u.set_password('x'); u.save()

    c = Client()
    assert c.login(username='buyer', password='x')

    # Simuler l'enrôlement (Phase 4 pluggable) via session entitlement
    s = c.session
    entitled = set(s.get('entitled_course_ids', []))
    entitled.add(course.id)
    s['entitled_course_ids'] = list(entitled)
    s.save()

    url = reverse('content:lecture', kwargs={'course_slug': course.slug, 'section_order': sec.order, 'lecture_order': lec.order})
    r = c.get(url)
    assert r.status_code == 200, f"Enrolled user should access premium, got {r.status_code}"

    print('== gating_authenticated: OK ✅ ==')