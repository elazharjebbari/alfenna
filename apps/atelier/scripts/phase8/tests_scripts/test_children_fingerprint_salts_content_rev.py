from __future__ import annotations
import copy
from django.test.client import RequestFactory
from django.contrib.auth.models import AnonymousUser
from apps.atelier.compose import pipeline
from apps.atelier.config.loader import load_config, clear_config_cache
from apps.common.runscript_harness import binary_harness

@binary_harness
def run():
    print("=== phase8/children_fingerprint_salts_content_rev ===")
    rf = RequestFactory()
    req = rf.get("/")
    req.user = AnonymousUser()

    # build v1
    ctx1 = pipeline.build_page_spec("online_home", req)
    head1 = ctx1["slots"]["header"]
    rev1 = head1.get("content_rev") or ""
    # Simule un override enfant en mémoire (sans toucher disque): on change params du child 'main'
    ctx1b = copy.deepcopy(ctx1)
    ctx1b["slots"]["header"]["children"]["main"]["params"]["_debug"] = "x"
    # Recalcule localement la portion fingerprint: on reconstruit la key via render_slot_fragment qui relira slot_ctx
    html1 = pipeline.render_slot_fragment(ctx1, head1, req)["html"]
    assert rev1 and len(rev1) > 0

    # rebuild page_ctx (la conf réelle est la même, mais nous vérifions la mécanique de rev par slot)
    ctx2 = pipeline.build_page_spec("online_home", req)
    head2 = ctx2["slots"]["header"]
    rev2 = head2.get("content_rev") or ""
    # Les revs doivent être de la forme "v1|ch:xxxxx"
    assert "|ch:" in rev1 and "|ch:" in rev2, "content_rev salée attendue"
    print("rev1 =", rev1)
    print("rev2 =", rev2)
