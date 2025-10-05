
"""
Rend la home via pipeline et vérifie 3 slots rendus + injection assets.
Exécution: python manage.py runscript pipeline_online_home_smoke
"""
from django.test.client import RequestFactory
from django.contrib.auth.models import AnonymousUser
from apps.atelier.compose import pipeline
from apps.common.runscript_harness import binary_harness

@binary_harness
def run():
    print("=== pipeline_online_home_smoke ===")
    rf = RequestFactory()
    req = rf.get("/")
    req.user = AnonymousUser()

    page_ctx = pipeline.build_page_spec("online_home", req)
    assert page_ctx, "page_ctx vide"
    # slots attendus (au moins)
    expected = {"header", "hero", "footer"}
    slots = set(page_ctx.get("slots", {}).keys())
    assert expected.issubset(slots), f"Slots attendus manquants. Vu: {slots}"

    fragments = {}
    for slot_id in expected:
        frag = pipeline.render_slot_fragment(page_ctx, page_ctx["slots"][slot_id], req)
        assert isinstance(frag, dict) and "html" in frag, f"Fragment invalide pour {slot_id}"
        assert frag["html"] is not None, f"HTML None pour {slot_id}"
        fragments[slot_id] = frag
        print(f"[OK] slot={slot_id} rendered ({len(frag['html'])} chars)")

    assets = pipeline.collect_page_assets(page_ctx)
    assert "css" in assets and "js" in assets and "head" in assets
    print(f"Assets: css={len(assets['css'])} js={len(assets['js'])} head={len(assets['head'])}")

    print("=> Pipeline smoke OK ✅")