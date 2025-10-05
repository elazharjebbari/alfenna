# apps/content/scripts/gating_policy.py
from django.test import Client
from django.urls import reverse
from django.contrib.auth.models import User
from apps.catalog.models.models import Course
from apps.content.models import Section, Lecture, LectureType
from apps.common.runscript_harness import binary_harness

def _ensure_course():
    course, _ = Course.objects.get_or_create(
        slug='gating-demo',
        defaults={
            'title': 'Gating Demo',
            'description': 'Demo free vs premium',
            'is_published': True,
            'free_lectures_count': 2,
        }
    )
    s1, _ = Section.objects.get_or_create(course=course, order=1, defaults={'title': 'S1', 'is_published': True})
    s2, _ = Section.objects.get_or_create(course=course, order=2, defaults={'title': 'S2', 'is_published': True})
    Lecture.objects.get_or_create(course=course, section=s1, order=1, defaults={'title': 'L1', 'type': LectureType.ARTICLE, 'is_published': True, 'is_free': True})
    Lecture.objects.get_or_create(course=course, section=s1, order=2, defaults={'title': 'L2', 'type': LectureType.ARTICLE, 'is_published': True, 'is_free': True})
    Lecture.objects.get_or_create(course=course, section=s2, order=1, defaults={'title': 'L3', 'type': LectureType.ARTICLE, 'is_published': True})
    return course


@binary_harness
def run(*args):
    print('== gating_policy: start ==')
    c = Client()
    course = _ensure_course()

    def lecture_url(sec, lec):
        return reverse('content:lecture', kwargs={'course_slug': course.slug, 'section_order': sec, 'lecture_order': lec})

    # Anonyme: L1 (1) → OK
    r = c.get(lecture_url(1, 1))
    assert r.status_code == 200, f"Anon should access L1, got {r.status_code}"

    # Anonyme: L2 (2) → OK
    r = c.get(lecture_url(1, 2))
    assert r.status_code == 200, f"Anon should access L2, got {r.status_code}"

    # Anonyme: L3 (3) → redirect 302 vers page cours (premium)
    r = c.get(lecture_url(2, 1), follow=False)
    assert r.status_code in (302, 403), f"Anon L3 should be locked, got {r.status_code}"

    # Staff preview: accès total même si on force preview=1
    staff, _ = User.objects.get_or_create(username='staff', defaults={'is_staff': True, 'is_superuser': True})
    staff.set_password('x'); staff.save()
    assert c.login(username='staff', password='x')
    r = c.get(lecture_url(2, 1) + '?preview=1')
    assert r.status_code == 200, f"Staff preview should access, got {r.status_code}"

    print('== gating_policy: OK ✅ ==')