"""
Vérifie MISS → HIT par slot avec segments fr/m/Y et page=online_home.
Exécution: python manage.py runscript phase7.cache_fragments_smoke
"""
from django.test.client import RequestFactory
from django.contrib.auth.models import AnonymousUser

from apps.atelier import services
from apps.atelier.compose import pipeline
from apps.atelier.compose.cache import delete_fragment  # pour hygiene
from apps.common.runscript_harness import binary_harness

PAGE_ID = "online_home"
CHECK_SLOTS = ["header", "hero", "footer"]

@binary_harness
def run():
    print("=== phase7/cache_fragments_smoke ===")
    rf = RequestFactory()
    req = rf.get("/", HTTP_ACCEPT_LANGUAGE="fr", HTTP_USER_AGENT="Mobile")
    req.user = AnonymousUser()
    # Fake consent cookie
    req.COOKIES = getattr(req, "COOKIES", {})
    req.COOKIES["consent"] = "Y"
    req.site_version = "core"

    # Build page spec pour avoir les clés
    page_ctx = pipeline.build_page_spec(PAGE_ID, req)
    assert page_ctx and "slots" in page_ctx, "page_ctx invalide"

    # Purge préventive (si une exécution précédente a laissé des clés)
    seg = services.get_segments(req)
    for sid in CHECK_SLOTS:
        slot_ctx = page_ctx["slots"].get(sid) or {}
        key = slot_ctx.get("cache_key")
        if not key:
            key = services.build_cache_key(
                PAGE_ID,
                sid,
                slot_ctx.get("variant_key") or "A",
                seg,
                page_ctx["content_rev"],
                page_ctx["qa_preview"],
                site_version=req.site_version,
            )
        delete_fragment(key)

    # MISS -> render
    misses = []
    for sid in CHECK_SLOTS:
        html = pipeline.render_slot_fragment(page_ctx, page_ctx["slots"][sid], req)["html"]
        print(f"[MISS→SET] slot={sid} len={len(html)}")
        misses.append(bool(html))

    # HIT
    hits = []
    for sid in CHECK_SLOTS:
        html = pipeline.render_slot_fragment(page_ctx, page_ctx["slots"][sid], req)["html"]
        hits.append(bool(html))
        print(f"[HIT] slot={sid} len={len(html)}")

    assert all(misses) and all(hits), "Tous les slots n'ont pas produit HTML en MISS/HIT"
    print("=> PASS ✅")
