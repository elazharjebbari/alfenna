# apps/content/scripts/gating_no_leak.py
from django.test import Client
from django.urls import reverse
from apps.catalog.models.models import Course
from apps.common.runscript_harness import binary_harness


@binary_harness
def run(*args):
    print('== gating_no_leak: start ==')
    c = Client()

    course = Course.objects.filter(is_published=True).first()
    assert course, 'Aucun cours publié. Seed un cours.'

    # prendre arbitrairement la 3e leçon si elle existe
    sections = list(course.sections.order_by('order'))
    assert sections, 'Aucune section'
    target_url = None
    count = 0
    for s in sections:
        for lec in s.lectures.order_by('order'):
            count += 1
            if count == (int(course.free_lectures_count or 0) + 1):
                target_url = reverse('content:lecture', kwargs={'course_slug': course.slug, 'section_order': s.order, 'lecture_order': lec.order})
                premium_title = lec.title
                break
        if target_url:
            break

    assert target_url, 'Pas assez de leçons pour tester la fuite premium'

    r = c.get(target_url)
    # Le template de redirection ne doit pas contenir le titre de la leçon premium si on ne l'affiche pas
    # On accepte la redirection 302 vers la page cours.
    assert r.status_code in (302, 403), f"Attendu refus/redirect, reçu {r.status_code}"

    if r.status_code == 200:
        assert premium_title.encode() not in r.content, 'Fuite: le contenu premium est présent dans le HTML'

    print('== gating_no_leak: OK ✅ ==')