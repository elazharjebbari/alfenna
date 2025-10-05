from django.utils import timezone
from apps.catalog.models.models import Course
from apps.content.models import Section, Lecture, LectureType

def run(*args):
    print("== catalog_seed: start ==")

    course, created = Course.objects.get_or_create(
        slug='django-fondamentaux',
        defaults={
            'title': 'Django Fondamentaux',
            'description': 'Apprenez Django de A à Z. Vidéos, articles, PDFs.',
            'seo_title': 'Formation Django — Fondamentaux',
            'seo_description': 'Parcours complet: modèles, vues, templates, ORM.',
            'is_published': True,
            'published_at': timezone.now(),
            'free_lectures_count': 2,
        }
    )

    # Sections
    s1, _ = Section.objects.get_or_create(course=course, order=1, defaults={'title': 'Prise en main', 'is_published': True})
    s2, _ = Section.objects.get_or_create(course=course, order=2, defaults={'title': 'Modèles & ORM', 'is_published': True})

    # Leçons
    Lecture.objects.get_or_create(course=course, section=s1, order=1, defaults={'title': 'Installer Django', 'type': LectureType.ARTICLE, 'is_published': True, 'is_free': True})
    Lecture.objects.get_or_create(course=course, section=s1, order=2, defaults={'title': 'Démarrer un projet', 'type': LectureType.VIDEO, 'is_published': True, 'is_free': True})
    Lecture.objects.get_or_create(course=course, section=s2, order=1, defaults={'title': 'Modèles et migrations', 'type': LectureType.PDF, 'is_published': True})

    print(f"Seed OK — Course id={course.id} slug={course.slug}")
    print("== catalog_seed: OK ✅ ==")