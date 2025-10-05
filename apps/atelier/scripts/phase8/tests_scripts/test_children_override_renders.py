from __future__ import annotations
from django.test.client import RequestFactory
from django.contrib.auth.models import AnonymousUser
from django.core.management.base import CommandError
from apps.atelier.compose import pipeline
from apps.atelier.config.loader import load_config, clear_config_cache
from apps.common.runscript_harness import binary_harness

@binary_harness
def run():
    print("=== phase8/children_override_renders ===")
    rf = RequestFactory()
    req = rf.get("/")
    req.user = AnonymousUser()

    page_ctx = pipeline.build_page_spec("online_home", req)
    assert page_ctx and "slots" in page_ctx
    header = page_ctx["slots"]["header"]
    # en l'état, pas d'overrides explicites dans pages.yml mais on doit au moins rendre les enfants du manifest
    html = pipeline.render_slot_fragment(page_ctx, header, req)["html"]
    assert "header-main-wrapper" in html, "header/main non injecté"
    assert 'id="mobileMenu"' in html, "header/mobile non injecté"
    print("=> OK")
