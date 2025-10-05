from __future__ import annotations
import json
import difflib
from typing import Any, Dict, List, Tuple, Mapping, Optional

from django.conf import settings
from django.test.client import RequestFactory
from django.urls import reverse, NoReverseMatch, get_resolver

from apps.atelier.components import discovery as comp_discovery
from apps.atelier.components.registry import get as get_component, all_aliases, NamespaceComponentMissing
from apps.atelier.compose.hydration import load as hydrate
from apps.common.runscript_harness import binary_harness


# ======= Décorations CLI =======
RST = "\033[0m"
B  = "\033[1m"
DIM= "\033[2m"
RED= "\033[31m"
GRN= "\033[32m"
YLW= "\033[33m"
BLU= "\033[34m"
CYN= "\033[36m"
GRY= "\033[90m"

I_OK   = f"{GRN}✅{RST}"
I_FAIL = f"{RED}❌{RST}"
I_WARN = f"{YLW}⚠️ {RST}"
I_INFO = f"{CYN}ℹ️ {RST}"
I_FIND = f"{BLU}🔎{RST}"
I_LINK = f"🔗"
I_GEAR = f"🧩"
I_STEP = f"🧭"
I_TREE = f"🌿"
I_JSON = f"🧾"
I_BUL  = f"•"
I_SUB  = f"↳"


def hr(title: str) -> None:
    print(f"\n{B}{title}{RST}")
    print(f"{GRY}{'─'*len(title)}{RST}")


def pretty(obj: Any) -> str:
    try:
        return json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True)
    except Exception:
        return repr(obj)


def as_mapping(v: Any) -> Mapping[str, Any]:
    return v if isinstance(v, Mapping) else {}


def deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = dict(base or {})
    for k, v in (override or {}).items():
        if k in out and isinstance(out[k], Mapping) and isinstance(v, Mapping):
            out[k] = deep_merge(out[k], v)  # type: ignore
        else:
            out[k] = v
    return out


# ======= Inspection des routes =======
def all_url_names() -> List[str]:
    resolver = get_resolver()
    names: List[str] = []
    def walk(patterns):
        for p in patterns:
            if hasattr(p, "url_patterns"):
                walk(p.url_patterns)
            else:
                name = getattr(p, "name", None)
                if name:
                    # Si un namespace parent existe, Django l’inclut déjà dans name (ex: "pages:home")
                    names.append(name)
    walk(resolver.url_patterns)
    return sorted(set(names))


def suggest_names(target: str, pool: List[str], n: int = 5) -> List[str]:
    if not target:
        return []
    return difflib.get_close_matches(target, pool, n=n)


def try_reverse(url_name: str, url_kwargs: Optional[dict] = None) -> Tuple[bool, str]:
    try:
        if url_kwargs:
            return True, reverse(url_name, kwargs=url_kwargs)
        return True, reverse(url_name)
    except NoReverseMatch as e:
        return False, f"NoReverseMatch: {e}"
    except Exception as e:
        return False, f"Error: {e}"


# ======= Vérification d’une entrée de menu =======
def check_menu_item(item: Mapping[str, Any], all_names: List[str], prefix: str = "") -> None:
    label = (item.get("label") or "").strip()
    url = (item.get("url") or "").strip()
    url_name = (item.get("url_name") or "").strip()
    url_kwargs = item.get("url_kwargs") if isinstance(item.get("url_kwargs"), dict) else None

    print(f"  {I_BUL} {prefix}{B}{label or '(sans label)'}{RST}")

    if url:
        # URL directe
        if url.startswith("/") or url.startswith("http"):
            print(f"     {I_LINK} URL directe: {GRN}{url}{RST}")
        else:
            print(f"     {I_WARN} URL non absolue: '{url}' → risque d’être traitée comme relative")
    elif url_name:
        ok, res = try_reverse(url_name, url_kwargs)
        if ok:
            print(f"     {I_LINK} {GRN}{url_name}{RST} → {res}")
        else:
            print(f"     {I_FAIL} reverse('{url_name}') impossible: {RED}{res}{RST}")
            sugg = suggest_names(url_name, all_names)
            if sugg:
                print(f"     {I_FIND} suggestions proches: {', '.join(sugg)}")
    else:
        print(f"     {I_WARN} ni 'url' ni 'url_name' — fallback probable sur ‘#’")


def check_menu_block(menu: Any, all_names: List[str], title: str) -> None:
    print(f"{I_TREE} {B}{title}{RST}")
    if not isinstance(menu, list) or not menu:
        print(f"  {I_WARN} menu vide ou mal typé (attendu: list)")
        return
    for it in menu:
        if not isinstance(it, Mapping):
            print(f"  {I_WARN} entrée ignorée (type={type(it).__name__})")
            continue
        check_menu_item(it, all_names)
        # enfants ?
        children = it.get("children")
        if isinstance(children, list) and children:
            for sub in children:
                if isinstance(sub, Mapping):
                    check_menu_item(sub, all_names, prefix=f"{I_SUB} ")
                else:
                    print(f"     {I_WARN} enfant ignoré (type={type(sub).__name__})")


# ======= Lecture manifests =======
def read_manifest_params(alias: str) -> Dict[str, Any]:
    comp = get_component(alias, namespace=NAMESPACE, fallback=False)
    return dict(comp.get("params") or {})


def read_manifest_hydrator(alias: str) -> Tuple[str, str]:
    comp = get_component(alias, namespace=NAMESPACE, fallback=False)
    hyd = as_mapping(comp.get("hydrate"))
    module = (hyd.get("module") or "").strip()
    func = (hyd.get("func") or "").strip()
    return module, func


# ======= Exécution principale =======
@binary_harness
def run():
    hr("DISCOVERY")
    count, warns = comp_discovery.discover(override_existing=True)
    if warns:
        for w in warns:
            print(f"{I_WARN} {w}")
    print(f"{I_INFO} components discovered: {count}")

    targets = ["header/struct", "header/main", "header/mobile"]
    missing = []
    for a in targets:
        try:
            get_component(a, namespace=NAMESPACE, fallback=False)
        except NamespaceComponentMissing:
            missing.append(a)
    if missing:
        print(f"{I_FAIL} alias manquants dans le registre: {', '.join(missing)}")
        return

    hr("REGISTRY SNAPSHOT")
    for a in targets:
        comp = get_component(a, namespace=NAMESPACE, fallback=False)
        print(f"{I_OK} {B}{a}{RST} → template={comp.get('template')}")
        module, func = read_manifest_hydrator(a)
        if module and func:
            print(f"   {I_GEAR} hydrate: {module}.{func}")
        else:
            print(f"   {I_GEAR} hydrate: (aucun)")

    hr("URL NAMES CATALOG")
    names = all_url_names()
    print(f"{I_INFO} {len(names)} noms de routes chargés.")
    # Affiche un petit extrait utile (home/login/register/faq/course)
    probe = [n for n in names if any(k in n for k in ("home", "login", "register", "faq", "course", "pages"))]
    if probe:
        print(f"{DIM}{I_JSON} aperçu: {', '.join(probe[:20])}{RST}")

    rf = RequestFactory()
    request = rf.get("/__header_routes_trace__/")
    request.site_version = NAMESPACE

    # ============ HEADER/MAIN ============
    hr("HEADER/MAIN — PARAMS MANIFEST (BRUTS)")
    p_main = read_manifest_params("header/main")
    print(pretty(p_main))

    check_menu_block(p_main.get("menu"), names, "Menu (manifest brut)")

    hr("HEADER/MAIN — CONTEXTE APRÈS HYDRATATION (manifest-first)")
    ctx_main = hydrate("header/main", request, params={}, namespace=NAMESPACE)
    print(pretty({k: ctx_main.get(k) for k in ("logo_src","logo_alt","home_url","show_auth_links")}))
    menu_ctx = ctx_main.get("menu")
    check_menu_block(menu_ctx, names, "Menu (après hydration)")

    # ============ HEADER/MOBILE ============
    hr("HEADER/MOBILE — PARAMS MANIFEST (BRUTS)")
    p_mobile = read_manifest_params("header/mobile")
    print(pretty({k: p_mobile.get(k) for k in ("login_url","register_url")}))
    check_menu_block(p_mobile.get("menu"), names, "Menu mobile (manifest brut)")

    hr("HEADER/MOBILE — CONTEXTE APRÈS HYDRATATION (manifest-first)")
    ctx_m = hydrate("header/mobile", request, params={}, namespace=NAMESPACE)
    print(pretty({k: ctx_m.get(k) for k in ("login_url","register_url")}))
    check_menu_block(ctx_m.get("menu"), names, "Menu mobile (après hydration)")

    # ============ HEADER/STRUCT ============
    hr("HEADER/STRUCT — PARAMS MANIFEST (BRUTS)")
    p_struct = read_manifest_params("header/struct")
    print(pretty({k: p_struct.get(k) for k in ("topbar","contact")}))
    module, func = read_manifest_hydrator("header/struct")
    if not (module and func):
        print(f"{I_WARN} aucun hydratateur pour header/struct (ok si volontaire).")
    ctx_s = hydrate("header/struct", request, params={}, namespace=NAMESPACE)
    print(pretty(ctx_s))

    # ============ CHECK ROUTES CRITIQUES ============
    hr("ROUTES CRITIQUES — AUTH & HOME")
    critical = [
        ("home", "pages:home", None),
        ("login", "login", None),
        ("register", "register", None),
        ("logout", "logout", None),
        ("profile", "profile", None),
        ("onlinelearning-home", "onlinelearning-home", None),
    ]
    for label, name, kwargs in critical:
        ok, res = try_reverse(name, kwargs)
        if ok:
            print(f"{I_OK} {label}: reverse('{name}') → {res}")
        else:
            print(f"{I_FAIL} {label}: reverse('{name}') → {res}")
            sugg = suggest_names(name, names)
            if sugg:
                print(f"   {I_FIND} suggestions: {', '.join(sugg)}")

    # Résumé & conseils
    hr("SYNTHÈSE")
    print(f"{I_STEP} Lis les blocs ‘{B}Menu (manifest brut){RST}’ puis ‘{B}Menu (après hydration){RST}’.")
    print(f"   {I_INFO} Si un item a {I_FAIL} reverse(...), corrige le {B}url_name{RST} dans le manifest,")
    print(f"           ou assure-toi que la route existe (cf. suggestions).")
    print(f"   {I_INFO} Si un item n’a ni url ni url_name → le template tombera sur ‘#’.")
    print(f"   {I_INFO} Pour auth links, vérifie que ‘login’/‘register’ sont exposés.")
    print(f"\n{I_OK} Trace terminée.")
NAMESPACE = "core"
