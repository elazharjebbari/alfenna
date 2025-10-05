"""
Vérifie que dans UNE même requête, un second rendu du même fragment
est servi depuis le L1 request-local (l1_hits augmente, backend_hits n'augmente pas).
Exécution: python manage.py runscript phase7.l1_request_cache_idempotency
"""
from django.test.client import RequestFactory
from django.contrib.auth.models import AnonymousUser

from apps.atelier import services
from apps.atelier.compose import pipeline
from apps.atelier.compose.cache import delete_fragment
from apps.common.runscript_harness import binary_harness

PAGE_ID = "online_home"
SLOT = "hero"

@binary_harness
def run():
    print("=== phase7/l1_request_cache_idempotency ===")
    rf = RequestFactory()
    req = rf.get("/", HTTP_ACCEPT_LANGUAGE="fr", HTTP_USER_AGENT="Mozilla/5.0")
    req.user = AnonymousUser()
    req.COOKIES = {"consent": "Y"}

    page_ctx = pipeline.build_page_spec(PAGE_ID, req)
    slot_ctx = page_ctx["slots"][SLOT]

    # Purge backend
    key = slot_ctx.get("cache_key") or ""
    if key:
        delete_fragment(key)

    # 1er rendu -> MISS backend, set backend, stats backend_sets=1
    html1 = pipeline.render_slot_fragment(page_ctx, slot_ctx, req)["html"]
    stats = services.get_cache_stats(req)
    print("stats after first:", stats)
    assert stats["backend_sets"] >= 1, "Le premier rendu doit setter le backend"
    assert len(html1) > 0

    # Reset stats pour isoler la 2e lecture
    req._atelier_cache_stats = {"l1_hits": 0, "backend_hits": 0, "backend_sets": 0}

    # 2e rendu dans la même requête -> L1
    html2 = pipeline.render_slot_fragment(page_ctx, slot_ctx, req)["html"]
    stats2 = services.get_cache_stats(req)
    print("stats second:", stats2)
    assert stats2["l1_hits"] >= 1 and stats2["backend_hits"] == 0, "Le second rendu doit venir du L1"
    assert html2 == html1
    print("=> PASS ✅")