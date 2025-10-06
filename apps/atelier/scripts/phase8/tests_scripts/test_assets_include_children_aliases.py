from __future__ import annotations
from django.test.client import RequestFactory
from django.contrib.auth.models import AnonymousUser
from apps.atelier.compose import pipeline
from apps.common.runscript_harness import binary_harness

@binary_harness
def run():
    print("=== phase8/assets_include_children_aliases ===")
    rf = RequestFactory()
    req = rf.get("/")
    req.user = AnonymousUser()

    page_ctx = pipeline.build_page_spec("online_home", req)
    assets = pipeline.collect_page_assets(page_ctx)
    # Doit inclure au moins le CSS du header + mobile-menu
    css = " ".join(assets.get("css") or [])
    assert "components/header/mobile-menu.css" in css, "Assets enfants non agrégés"
    print("[OK] assets include children aliases")
