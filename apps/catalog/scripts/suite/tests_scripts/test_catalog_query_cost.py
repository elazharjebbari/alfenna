from django.test import Client
from django.urls import reverse
from django.db import connection
from django.test.utils import CaptureQueriesContext
from apps.catalog.models.models import Course
from apps.common.runscript_harness import binary_harness

LIST_MAX_Q = 10
DETAIL_MAX_Q = 20

@binary_harness
def run(*args):
    print("== catalog_query_cost: start ==")
    c = Client()

    # Liste
    with CaptureQueriesContext(connection) as ctx:
        resp = c.get(reverse('catalog:list'))
        assert resp.status_code == 200, f"Liste status {resp.status_code}"
    print(f"Liste: {len(ctx)} requêtes")
    assert len(ctx) <= LIST_MAX_Q, f"Trop de requêtes sur la liste: {len(ctx)} > {LIST_MAX_Q}"

    # Détail
    course = Course.objects.first()
    assert course, "Aucun cours en base. Exécute catalog_seed."
    with CaptureQueriesContext(connection) as ctx2:
        resp = c.get(course.get_absolute_url())
        assert resp.status_code == 200, f"Detail status {resp.status_code}"
    print(f"Détail: {len(ctx2)} requêtes")
    assert len(ctx2) <= DETAIL_MAX_Q, f"Trop de requêtes sur le détail: {len(ctx2)} > {DETAIL_MAX_Q}"

    print("== catalog_query_cost: OK ✅ ==")