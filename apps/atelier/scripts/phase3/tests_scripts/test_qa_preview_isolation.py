"""
Vérifie que le mode preview QA isole le cache (clés distinctes).
Exécution: python manage.py runscript qa_preview_isolation
"""
from django.test.client import RequestFactory
from django.contrib.auth.models import AnonymousUser
from apps.atelier.compose import pipeline, cache
from apps.common.runscript_harness import binary_harness

@binary_harness
def run():
    print("=== qa_preview_isolation ===")
    rf = RequestFactory()

    # Request standard
    req_std = rf.get("/")
    req_std.user = AnonymousUser()
    page_std = pipeline.build_page_spec("online_home", req_std)
    hero_std = page_std["slots"]["hero"]
    key_std = hero_std.get("cache_key") or "none"

    # Request preview (flag QA forcé via query param géré par pipeline/waffle)
    req_preview = rf.get("/?dwft_hero_v2=1")
    req_preview.user = AnonymousUser()
    page_prev = pipeline.build_page_spec("online_home", req_preview)
    hero_prev = page_prev["slots"]["hero"]
    key_prev = hero_prev.get("cache_key") or "none"

    print("key_std =", key_std)
    print("key_prev =", key_prev)
    assert key_std != key_prev, "Clés cache identiques: la preview QA pollue le cache public"
    print("=> QA preview isolation OK ✅")