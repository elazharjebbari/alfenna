from __future__ import annotations
import json
from pathlib import Path
from types import SimpleNamespace

from django.core.management.base import CommandError
from django.template.loader import render_to_string

from apps.atelier.components import discovery
from apps.atelier.components.registry import get as get_component
from apps.atelier.compose import pipeline
from apps.atelier.config.registry import get_page_spec
from apps.common.runscript_harness import binary_harness

OUT = Path("reports/debug/slider"); OUT.mkdir(parents=True, exist_ok=True)

def _fake_request():
    req = SimpleNamespace()
    req.request_id = "smoke-slider"
    req.headers = {"Accept-Language": "fr"}
    req.META = {"HTTP_USER_AGENT": "smoke"}
    req.GET = {}
    req.COOKIES = {}
    req.user = SimpleNamespace(is_authenticated=False, first_name="", username="")
    req._segments = SimpleNamespace(lang="fr", device="d", consent="N", source="", campaign="", qa=False)
    req.site_version = "core"
    return req

@binary_harness
def run():
    print("== Slider (hero/cover) smoke ==")

    # 1) discovery/registry
    count, warns = discovery.discover(override_existing=True)
    print(f"discovery.count={count}, warns={len(warns)}")
    for w in warns: print("  warn:", w)

    comp = get_component("hero/cover", namespace="core")
    if not comp:
        raise CommandError("Composant 'hero/cover' introuvable au registre.")

    print("registry.meta:", json.dumps(comp, ensure_ascii=False, indent=2))

    # 2) hydratation manifest-only
    from apps.atelier.compose.hydration import load as hydrate
    req = _fake_request()
    ctxA = hydrate("hero/cover", req, params={}, namespace="core")
    price = ctxA.get("price")
    if not price or int(price) <= 0:
        raise CommandError(f"Hydratation KO: price invalide ({price})")
    print(f"[A] hydrate price={price}")

    # 3) rendu direct (template + ctxA)
    html_direct = render_to_string(comp["template"], ctxA, request=req)
    (OUT / "direct.html").write_text(html_direct, encoding="utf-8")
    if "slider-section" not in html_direct or f"{price} Dhs" not in html_direct:
        raise CommandError("Render direct KO: marqueurs non trouvés.")
    print("[OK] render direct → reports/debug/slider/direct.html")

    # 4) pipeline: depuis la page online_home
    ps = get_page_spec("online_home", namespace="core")
    if not ps:
        raise CommandError("Page 'online_home' introuvable.")
    page_ctx = pipeline.build_page_spec("online_home", req)
    slot = page_ctx["slots"].get("hero")
    if not slot:
        raise CommandError("Slot 'hero' absent de la page.")

    frag = pipeline.render_slot_fragment(page_ctx, slot, req)["html"]
    (OUT / "pipeline.html").write_text(frag, encoding="utf-8")
    if "slider-section" not in frag or f"{price} Dhs" not in frag:
        raise CommandError("Render pipeline KO: marqueurs non trouvés.")
    print("[OK] render pipeline → reports/debug/slider/pipeline.html")

    print("== SUCCESS ==")
