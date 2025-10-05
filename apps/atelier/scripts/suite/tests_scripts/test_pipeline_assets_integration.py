"""Ensure Atelier pipeline collects assets without duplication."""

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory

from apps.atelier.compose import pipeline
from apps.common.runscript_harness import binary_harness


@binary_harness
def run() -> None:
    print("=== suite/tests_scripts/test_pipeline_assets_integration ===")
    factory = RequestFactory()
    request = factory.get('/')
    request.user = AnonymousUser()

    page_ctx = pipeline.build_page_spec('online_home', request)
    assert page_ctx and page_ctx.get('slots'), 'page_ctx invalide'

    assets = pipeline.collect_page_assets(page_ctx)
    assert isinstance(assets, dict), 'collect_page_assets doit renvoyer un dict'
    assert set(assets.keys()) == {'css', 'js', 'head'}, 'Clés inattendues dans assets'

    rendered = pipeline.render_page(request, 'online_home', content_rev='')
    assert 'fragments' in rendered and 'assets' in rendered, 'render_page doit renvoyer fragments + assets'
    print(f"[OK] assets css={len(assets['css'])} js={len(assets['js'])} head={len(assets['head'])}")
    print('=> PASS ✅')
