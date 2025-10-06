from django.db.models import Count
from apps.content.models import Section, Lecture
from apps.common.runscript_harness import binary_harness

@binary_harness
def run(*args):
    print("== catalog_ordering: start ==")

    dup_sections = (
        Section.objects.values('course_id', 'order')
        .annotate(c=Count('id')).filter(c__gt=1)
    )
    assert not dup_sections.exists(), f"Doublons d'ordre section: {list(dup_sections)}"

    dup_lectures = (
        Lecture.objects.values('section_id', 'order')
        .annotate(c=Count('id')).filter(c__gt=1)
    )
    assert not dup_lectures.exists(), f"Doublons d'ordre lecture: {list(dup_lectures)}"

    # Vérifie séquences sans trous par section
    from django.db.models import Min, Max
    for section in Section.objects.all():
        orders = list(section.lectures.order_by('order').values_list('order', flat=True))
        if not orders:
            continue
        expected = list(range(1, len(orders) + 1))
        assert orders == expected, f"Trous ou incohérences dans section {section.id}: {orders} vs {expected}"

    print("== catalog_ordering: OK ✅ ==")