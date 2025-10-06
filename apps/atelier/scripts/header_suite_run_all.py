"""
Vérifie bout-à-bout le composant header et ses enfants :
- discovery (override)
- registry (3 alias)
- chemins d'hydrateurs importables
- templates résolubles
- hydratation: parent & enfants
- rendu direct: parent + enfants avec marqueurs attendus
- rendu pipeline: injection des enfants dans le parent
- header non cacheté (si exposé par la pipeline)
- logs très détaillés avec aides au debug

Exécution:
  python manage.py runscript header_suite_run_all
"""
from __future__ import annotations
import json
import re
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

from django.core.management.base import CommandError
from django.template.loader import get_template, render_to_string
from django.template import TemplateDoesNotExist
from django.test.client import RequestFactory
from django.contrib.auth.models import AnonymousUser

from apps.atelier.components import discovery
from apps.atelier.components.registry import (
    get as reg_get,
    exists as reg_exists,
    all_aliases,
    NamespaceComponentMissing,
)
from apps.atelier.compose import pipeline

OUTDIR = Path("reports/debug/header_suite"); OUTDIR.mkdir(parents=True, exist_ok=True)

ALIASES = {
    "parent": "header/struct",
    "main":   "header/main",
    "mobile": "header/mobile",
}

NAMESPACE = "core"

HYDRATE = {
    "module": "apps.atelier.compose.hydrators.header.hydrators",
    "funcs": {
        "header/struct": "header_struct",
        "header/main":   "header_main",
        "header/mobile": "header_mobile",
    }
}

def _fake_request():
    req = SimpleNamespace()
    req.request_id = "header-suite"
    req.headers = {"Accept-Language": "fr"}
    req.META = {"HTTP_USER_AGENT": "audit"}
    req.GET = {}
    req.COOKIES = {}
    req.user = AnonymousUser()
    req._segments = SimpleNamespace(lang="fr", device="d", consent="N", source="", campaign="", qa=False)
    req.site_version = NAMESPACE
    return req

def run():
    print("\n============ DISCOVERY ============")
    count, warns = discovery.discover(override_existing=True)
    for w in warns:
        print("[discover.warn]", w)
    print(f"discovery.count={count}, warns={len(warns)}")

    print("\n============ REGISTRY & HYDRATOR PATHS ============")
    # aliases
    for k, alias in ALIASES.items():
        if not reg_exists(alias, namespace=NAMESPACE, include_fallback=False):
            raise CommandError(f"Alias absent du registry: {alias}")
        meta = reg_get(alias, namespace=NAMESPACE, fallback=False)
        print(f"[OK] registry {alias} → template={meta.get('template')}")

    # hydrators importables
    module_path = HYDRATE["module"]
    try:
        mod = import_module(module_path)
        print(f"[OK] hydrate module importé: {module_path}")
    except Exception as e:
        raise CommandError(f"Import hydrator module KO: {module_path} ({e})")

    for alias, func_name in HYDRATE["funcs"].items():
        if not hasattr(mod, func_name):
            raise CommandError(f"Hydrator function manquante {module_path}.{func_name} pour {alias}")
        print(f"[OK] hydrator function présente: {module_path}.{func_name}")

    print("\n============ TEMPLATES ============")
    for alias in ALIASES.values():
        tpl = reg_get(alias, namespace=NAMESPACE, fallback=False).get("template")
        try:
            get_template(tpl)
            print(f"[OK] template résolu: {tpl}")
        except TemplateDoesNotExist as e:
            raise CommandError(f"Template introuvable pour {alias}: {tpl} ({e})")

    print("\n============ HYDRATION & DIRECT RENDER (CHILDREN) ============")
    req = _fake_request()

    # MAIN
    main_meta = reg_get(ALIASES["main"], namespace=NAMESPACE, fallback=False)
    main_tpl = main_meta["template"]
    main_hfunc = getattr(mod, HYDRATE["funcs"][ALIASES["main"]])
    ctx_main = main_hfunc(req, main_meta.get("params") or {})
    html_main = render_to_string(main_tpl, ctx_main, request=req)
    (OUTDIR / "child_main.html").write_text(html_main, encoding="utf-8")
    ok_main_marker = "header-main-wrapper" in html_main
    print(f"[MAIN] rendered → {OUTDIR/'child_main.html'} marker(header-main-wrapper)={ok_main_marker}")
    if not ok_main_marker:
        raise CommandError("child main rendu mais sans 'header-main-wrapper'")

    # MOBILE
    mob_meta = reg_get(ALIASES["mobile"], namespace=NAMESPACE, fallback=False)
    mob_tpl = mob_meta["template"]
    mob_hfunc = getattr(mod, HYDRATE["funcs"][ALIASES["mobile"]])
    ctx_mobile = mob_hfunc(req, mob_meta.get("params") or {})
    html_mobile = render_to_string(mob_tpl, ctx_mobile, request=req)
    (OUTDIR / "child_mobile.html").write_text(html_mobile, encoding="utf-8")
    ok_mobile_marker = re.search(r'id=[\'"]mobileMenu[\'"]', html_mobile) is not None
    print(f"[MOBILE] rendered → {OUTDIR/'child_mobile.html'} marker(id='mobileMenu')={ok_mobile_marker}")
    if not ok_mobile_marker:
        raise CommandError("child mobile rendu mais sans id='mobileMenu'")

    print("\n============ HYDRATION & DIRECT RENDER (PARENT) ============")
    parent_meta = reg_get(ALIASES["parent"], namespace=NAMESPACE, fallback=False)
    parent_tpl = parent_meta["template"]
    parent_hfunc = getattr(mod, HYDRATE["funcs"][ALIASES["parent"]])
    ctx_parent = parent_hfunc(req, parent_meta.get("params") or {})
    html_parent = render_to_string(parent_tpl, ctx_parent, request=req)
    (OUTDIR / "parent_direct.html").write_text(html_parent, encoding="utf-8")
    print(f"[PARENT] direct render → {OUTDIR/'parent_direct.html'} (sans injection enfants)")

    print("\n============ PIPELINE PAGE SLOT (INJECTION ENFANTS) ============")
    page_id = "online_home"
    page_ctx = pipeline.build_page_spec(page_id, req)
    header_slot = (page_ctx.get("slots") or {}).get("header")
    if not header_slot:
        raise CommandError("Slot 'header' absent de la page 'online_home'")

    # forcer no-cache pour audit lisible si l'API le permet via context local
    header_slot = dict(header_slot)
    header_slot["cache"] = False

    out = pipeline.render_slot_fragment(page_ctx, header_slot, req)
    html = out.get("html") or ""
    (OUTDIR / "parent_pipeline.html").write_text(html, encoding="utf-8")
    ok_inject_main = "header-main-wrapper" in html
    ok_inject_mobile = re.search(r'id=[\'"]mobileMenu[\'"]', html) is not None
    print(f"[PIPELINE] parent rendered → {OUTDIR/'parent_pipeline.html'} inject_main={ok_inject_main} inject_mobile={ok_inject_mobile}")

    if not (ok_inject_main and ok_inject_mobile):
        print("\n[HINT] Vérifie que 'components/header/header_struct.html' contient bien:")
        print("  {{ children.header_struct__main }} et {{ children.header_struct__mobile }}")
        print("  et que compose.children mappe main/mobile vers header/main & header/mobile.")
        raise CommandError("Injection enfants KO — voir indices ci-dessus.")

    print("\n============ CACHE (INFORMATIF) ============")
    # Si la pipeline expose cache/cache_key, on vérifie; sinon on log en info.
    cache_flag = header_slot.get("cache", None)
    cache_key = header_slot.get("cache_key", "")
    print(f"[INFO] header_slot.cache={cache_flag} cache_key({'present' if cache_key else 'absent'})")
    if cache_flag is False and not cache_key:
        print("[OK] header non cacheté (attendu).")
    else:
        print("[NOTE] La pipeline ne fournit pas d'indication claire de no-cache ici — observation, pas échec.")

    print("\n============ ASSETS (INFORMATIF) ============")
    assets = pipeline.collect_page_assets(page_ctx)
    print("assets keys:", list(assets.keys()))
    # Pas d'échec ici : on journalise seulement
    print(f"[INFO] assets sizes: css={len(assets.get('css', []))} js={len(assets.get('js', []))} head={len(assets.get('head', []))}")

    print("\n✅ HEADER SUITE — CHECK PASS COMPLET")
