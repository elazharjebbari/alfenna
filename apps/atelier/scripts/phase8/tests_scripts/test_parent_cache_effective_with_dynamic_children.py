from __future__ import annotations
from django.test.client import RequestFactory
from django.contrib.auth.models import AnonymousUser
from apps.atelier.compose import pipeline
from apps.common.runscript_harness import binary_harness

@binary_harness
def run():
    print("=== phase8/parent_cache_effective_with_dynamic_children ===")
    rf = RequestFactory()
    req = rf.get("/")
    req.user = AnonymousUser()

    page_ctx = pipeline.build_page_spec("online_home", req)
    header = page_ctx["slots"]["header"]
    # Avec manifest header/struct -> render.cacheable:false, le slot header doit être non-cacheable :
    assert header.get("cache") is False, "Le header doit être non-cacheable (dynamic auth_links)"
    assert not header.get("cache_key"), "cache_key du header doit être vide"
    html = pipeline.render_slot_fragment(page_ctx, header, req)["html"]
    assert "header-main-wrapper" in html
    print("=> OK")
