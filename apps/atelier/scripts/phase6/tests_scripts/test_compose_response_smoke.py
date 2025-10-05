"""
Vérifie que response.render_base produit une TemplateResponse exploitable,
avec un contexte compatible (slots_html fusionné slot+alias) et assets présents.
Exécution: python manage.py runscript phase6.compose_response_smoke
"""
from django.test.client import RequestFactory
from django.contrib.auth.models import AnonymousUser

from apps.atelier.compose import pipeline, response
from apps.common.runscript_harness import binary_harness

@binary_harness
def run():
    print("=== phase6/compose_response_smoke ===")
    rf = RequestFactory()
    req = rf.get("/")
    req.user = AnonymousUser()

    # 1) build page & fragments via pipeline
    page_ctx = pipeline.build_page_spec("online_home", req)
    frags = {}
    for sid, slot in (page_ctx.get("slots") or {}).items():
        rr = pipeline.render_slot_fragment(page_ctx, slot, req)
        frags[sid] = rr.get("html", "")

    assets = pipeline.collect_page_assets(page_ctx)

    # 2) compose a TemplateResponse
    resp = response.render_base(page_ctx, frags, assets, req)
    # force rendering
    resp.render()

    # 3) assertions de base
    assert resp.status_code == 200, f"Status inattendu: {resp.status_code}"
    ctx = resp.context_data or {}

    # 'slots_html' doit contenir les clés par slot ET par alias safe
    slots_html = ctx.get("slots_html") or {}
    for expected in ["header", "hero", "footer", "header_struct", "footer_main"]:
        assert expected in slots_html, f"slots_html['{expected}'] manquant"
        assert isinstance(slots_html[expected], str), f"slots_html['{expected}'] doit être str"

    page_assets = ctx.get("page_assets") or {}
    for k in ("css", "js", "head"):
        assert k in page_assets, f"page_assets.{k} absent"
        assert isinstance(page_assets[k], list), f"page_assets.{k} doit être list"

    print("=> PASS ✅")