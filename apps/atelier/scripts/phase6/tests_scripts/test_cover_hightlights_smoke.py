# apps/atelier/scripts/phase6/cover_highlights_autopsy.py
from __future__ import annotations
import json, re, time
from pathlib import Path
from typing import Any
from django.core.management.base import CommandError
from django.template.loader import render_to_string, get_template
from apps.atelier.components import discovery
from apps.atelier.components.registry import get as get_component, exists as comp_exists, NamespaceComponentMissing
from apps.atelier.compose.hydration import load as hydrate
from apps.atelier.components.contracts import validate as validate_contract, ContractValidationError
from apps.atelier.compose.pipeline import build_page_spec, render_slot_fragment
from apps.atelier import services
from apps.common.runscript_harness import binary_harness

ALIAS = "cover/highlights"
PAGE_ID = "online_home"
SLOT_ID = "cover"

def _mk_req():
    from types import SimpleNamespace
    try:
        from apps.atelier.middleware.segments import Segments
        seg = Segments(lang="fr", device="d", consent="N", source="", campaign="", qa=True)
    except Exception:
        seg = {"lang": "fr", "device": "d", "consent": "N", "source": "", "campaign": "", "qa": True}
    r = SimpleNamespace()
    r.request_id = f"autopsy-{int(time.time())}"
    r._segments = seg
    r.GET = {}
    r.COOKIES = {}
    r.META = {"HTTP_USER_AGENT": "autopsy"}
    r.headers = {"Accept-Language": "fr"}
    r.user = SimpleNamespace(is_authenticated=False, first_name="")
    r.site_version = "core"
    return r

def _count_cards(html: str) -> int:
    # Compte robuste: classe contenant 'card' sous guillemets simples OU doubles
    patt = r'class\s*=\s*(["\'])(?:(?!\1).)*\bcard\b(?:(?!\1).)*\1'
    return len(re.findall(patt, html or "", flags=re.IGNORECASE|re.DOTALL))

def _contains_fallback_alert(html: str) -> bool:
    return "Les points forts seront bientôt disponibles" in (html or "")

def _origin_name(tpl_obj) -> str:
    for path in ("origin.name", "template.origin.name", "engine.origin.name"):
        cur = tpl_obj
        try:
            for part in path.split("."):
                cur = getattr(cur, part)
            if isinstance(cur, str):
                return cur
        except Exception:
            pass
    return "(origin inconnu)"

def _write_debug(name: str, content: str) -> Path:
    out = Path("reports/debug/cover_highlights")
    out.mkdir(parents=True, exist_ok=True)
    p = out / name
    p.write_text(content or "", encoding="utf-8")
    return p

def _json_debug(name: str, data: Any) -> Path:
    return _write_debug(name, json.dumps(data, ensure_ascii=False, indent=2))

@binary_harness
def run():
    print("== Cover/highlights AUTOPSY ==")

    # (0) Discovery frais (override=True pour éviter les doublons silencieux)
    cnt, warns = discovery.discover(override_existing=True)
    print(f"discovery.count={cnt}, warns={len(warns)}")
    for w in warns:
        print(f"[discover.warn] {w}")

    # (1) Registry
    if not comp_exists(ALIAS, namespace="core", include_fallback=False):
        raise CommandError(f"Alias absent du registry: {ALIAS}")
    try:
        meta = get_component(ALIAS, namespace="core", fallback=False)
    except NamespaceComponentMissing as exc:
        raise CommandError(str(exc))
    print("registry.meta:", json.dumps(meta, ensure_ascii=False, indent=2))

    # (2) Template
    tname = meta.get("template")
    tpl = get_template(tname)
    print(f"template.resolved: {tname}")
    print(f"template.origin  : {_origin_name(tpl)}")

    # (3) Hydration (A/B/C)
    req = _mk_req()
    ctxA = hydrate(ALIAS, req, None, namespace="core")
    ctxB = hydrate(ALIAS, req, {"cards": []}, namespace="core")
    ctxC = hydrate(ALIAS, req, {"cards": [{"icon":"x","title":"T1","text":"t1"},{"icon":"y","title":"T2","text":"t2"}]}, namespace="core")

    _json_debug("ctxA.json", ctxA)
    _json_debug("ctxB.json", ctxB)
    _json_debug("ctxC.json", ctxC)

    print(f"[A] cards={len(ctxA.get('cards', []))} (manifest-only)")
    print(f"[B] cards={len(ctxB.get('cards', []))} (override=[])")
    print(f"[C] cards={len(ctxC.get('cards', []))} (override=2)")

    # (4) Contrat
    try:
        validate_contract(ALIAS, ctxA, namespace="core")
        print("[contract] OK (ctxA)")
    except ContractValidationError as e:
        raise CommandError(f"[contract] ERROR: {e}")

    # (5) Render DIRECT
    htmlA = render_to_string(tname, ctxA, request=req)
    pA = _write_debug("direct.html", htmlA)
    print(f"[render:direct] cards={_count_cards(htmlA)}, fallback_alert={_contains_fallback_alert(htmlA)} → {pA}")

    # Dump un extrait pour lecture console
    snippetA = htmlA.replace("\n"," ")[:3000]
    _write_debug("direct_snippet.txt", snippetA)

    # (6) Pipeline (cache OFF)
    pspec = build_page_spec(PAGE_ID, req)
    slot = dict((pspec.get("slots") or {}).get(SLOT_ID) or {})
    if not slot:
        raise CommandError(f"Slot '{SLOT_ID}' introuvable dans page '{PAGE_ID}'")
    slot["cache"] = False
    print("pipeline.slot:", json.dumps({"id":slot.get("id"),"alias":slot.get("alias"),"params":slot.get("params")}, ensure_ascii=False))

    frag = render_slot_fragment(pspec, slot, req)
    htmlP = frag.get("html","")
    pP = _write_debug("pipeline.html", htmlP)
    print(f"[render:pipeline] cards={_count_cards(htmlP)}, fallback_alert={_contains_fallback_alert(htmlP)} → {pP}")

    # (7) Clé cache *théorique*
    seg = services.get_segments(req)
    key = services.build_cache_key(PAGE_ID, SLOT_ID, slot.get("variant_key") or "A", seg, "v_diag", qa=True, site_version="core")
    fc = services.FragmentCache(request=req)
    print(f"[cache] exists={fc.exists(key)} key={key}")

    # (8) Verdict
    ca, cp = _count_cards(htmlA), _count_cards(htmlP)
    if ca == 0:
        raise CommandError("Direct render → 0 carte. Ouvre reports/debug/cover_highlights/direct.html et vérifie la présence des <div class='card …'>.")
    if cp == 0:
        raise CommandError("Pipeline render → 0 carte (cache OFF). Compare pipeline.html vs direct.html pour voir ce qui manque.")
    print("== SUCCESS: le composant rend des cartes en direct ET via la pipeline ==")
