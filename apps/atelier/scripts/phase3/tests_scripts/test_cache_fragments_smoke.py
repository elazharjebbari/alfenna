"""
Vérifie l'utilisation du cache fragment par slot (MISS puis HIT).
Exécution: python manage.py runscript cache_fragments_smoke
"""
from django.test.client import RequestFactory
from django.contrib.auth.models import AnonymousUser
from apps.atelier.compose import pipeline, cache
from apps.common.runscript_harness import binary_harness

@binary_harness
def run():
    print("=== cache_fragments_smoke ===")
    rf = RequestFactory()
    req = rf.get("/", HTTP_ACCEPT_LANGUAGE="fr")
    req.user = AnonymousUser()

    page_id = "online_home"
    page_ctx = pipeline.build_page_spec(page_id, req)
    assert page_ctx, "page_ctx vide"

    check_slots = ["header", "hero", "footer"]
    results = []

    # 1) First render → MISS (on force le rendu)
    for s in check_slots:
        slot_ctx = page_ctx["slots"][s]
        key = slot_ctx.get("cache_key") or f"{page_id}:{s}:debug"
        content = cache.get_fragment(key)
        print(f"{s} initial cache:", "HIT" if content else "MISS")
        frag = pipeline.render_slot_fragment(page_ctx, slot_ctx, req)  # devrait setter le cache si configuré
        results.append((s, key))

    # 2) Second round → devrait être HIT
    hits = []
    for s, key in results:
        content = cache.get_fragment(key)
        hits.append(bool(content))
        print(f"{s} second cache:", "HIT" if content else "MISS")

    assert all(hits), "Tous les slots ne sont pas en HIT au second passage"
    print("=> Cache fragments OK ✅")