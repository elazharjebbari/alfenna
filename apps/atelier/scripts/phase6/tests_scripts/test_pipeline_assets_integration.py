# apps/atelier/scripts/phase6/pipeline_assets_integration.py
from django.test.client import RequestFactory
from django.contrib.auth.models import AnonymousUser
from apps.atelier.compose import pipeline
from apps.common.runscript_harness import binary_harness

@binary_harness
def run():
    print("=== phase6/pipeline_assets_integration ===")
    rf = RequestFactory()
    req = rf.get("/")
    req.user = AnonymousUser()

    page_ctx = pipeline.build_page_spec("online_home", req)
    assert page_ctx and page_ctx.get("slots"), "page_ctx invalide"

    assets = pipeline.collect_page_assets(page_ctx)
    assert isinstance(assets, dict), "collect_page_assets doit renvoyer un dict"
    assert set(assets.keys()) == {"css", "js", "head"}, "Clés inattendues dans assets"

    rendered = pipeline.render_page(req, "online_home", content_rev="")
    assert "fragments" in rendered and "assets" in rendered, "render_page doit renvoyer fragments + assets"
    print(f"[OK] assets build={len(assets['css'])}/{len(assets['js'])}/{len(assets['head'])} ; render_page OK")
    print("=> PASS ✅")
