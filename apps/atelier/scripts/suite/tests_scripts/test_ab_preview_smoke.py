from django.test import RequestFactory
from apps.atelier.ab.waffle import apply_preview_override, resolve_variant
from apps.common.runscript_harness import binary_harness

@binary_harness
def run():
    rf = RequestFactory()
    req = rf.get("/?dwft_hero_v2=slider")
    apply_preview_override(req, "hero_v2")
    v, alias = resolve_variant("hero_v2", req)
    print("variant=", v, "alias=", alias)