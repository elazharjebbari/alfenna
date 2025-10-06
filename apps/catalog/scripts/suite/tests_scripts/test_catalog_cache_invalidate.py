from apps.catalog.models.models import Course
from apps.content.models import Section, Lecture
from apps.common.runscript_harness import binary_harness

@binary_harness
def run(*args):
    print("== catalog_cache_invalidate: start ==")

    course = Course.objects.first()
    assert course, "Aucun cours en base. Exécute catalog_seed."

    before = Course.objects.filter(pk=course.pk).values_list('plan_version', flat=True).get()

    # Ajouter une leçon → doit incrémenter plan_version via signal
    sec = course.sections.order_by('order').first()
    assert sec, "Le cours n'a pas de section. Seed manquant."
    Lecture.objects.create(course=course, section=sec, title='Nouvelle leçon (test)', order=999, is_published=True)

    after = Course.objects.filter(pk=course.pk).values_list('plan_version', flat=True).get()
    assert after == before + 1, f"plan_version n'a pas bougé: {before} -> {after}"

    print("== catalog_cache_invalidate: OK ✅ ==")