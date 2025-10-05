# apps/atelier/scripts/phase6/header_compose_audit.py
from __future__ import annotations
import json
import re
from pathlib import Path
from types import SimpleNamespace

from django.core.management.base import CommandError
from django.conf import settings
from django.template.loader import get_template, render_to_string
from django.template import TemplateDoesNotExist

from apps.atelier.components import discovery
from apps.atelier.components.registry import get as reg_get, all_aliases, NamespaceComponentMissing
from apps.atelier.config.registry import get_page_spec
from apps.atelier.compose import pipeline
from apps.common.runscript_harness import binary_harness

OUTDIR = Path("reports/debug/header_compose")


def _pp(label, obj):
    print(f"{label}: {json.dumps(obj, ensure_ascii=False, indent=2)}")


def _fake_request():
    req = SimpleNamespace()
    req.request_id = "audit-header"
    req.headers = {"Accept-Language": "fr"}
    req.META = {"HTTP_USER_AGENT": "audit"}
    req.GET = {}
    req.COOKIES = {}
    req.user = SimpleNamespace(is_authenticated=False, first_name="", username="")
    # Segments cohérents avec le middleware
    req._segments = SimpleNamespace(lang="fr", device="d", consent="N", source="", campaign="", qa=False)
    req.site_version = "core"
    return req


def _scan_all_manifests():
    files = []
    for root in discovery._template_roots():
        comp = Path(root) / "components"
        if not comp.exists():
            continue
        for mf in comp.rglob("*"):
            if mf.is_file() and mf.name in discovery.MANIFEST_FILENAMES:
                files.append(mf)
    return sorted(files)


def _group_by_alias(paths):
    groups = {}
    for p in paths:
        try:
            data = discovery._load_yaml(p)
            alias = (data.get("alias") or "").strip()
            if not alias:
                continue
            groups.setdefault(alias, []).append((p, data))
        except Exception:
            # on ignore les yaml invalides ici, la discovery formelle le signalera
            pass
    return groups


def _read_template_source(tpl_name: str) -> str:
    try:
        tpl = get_template(tpl_name)
    except TemplateDoesNotExist:
        return ""
    origin = getattr(tpl, "origin", None)
    if origin and origin.name:
        try:
            return Path(origin.name).read_text(encoding="utf-8")
        except Exception:
            return ""
    return ""


@binary_harness
def run():
    print("== Header COMPOSE audit ==")
    OUTDIR.mkdir(parents=True, exist_ok=True)

    # 1) Discover avec override=True pour refléter l'état réel attendu
    count, warns = discovery.discover(override_existing=True)
    print(f"discovery.count={count}, warns={len(warns)}")
    for w in warns:
        print(f"[WARN] {w}")

    # 2) Scanner le disque pour détecter d'éventuels doublons
    paths = _scan_all_manifests()
    print(f"manifests_on_disk={len(paths)}")
    by_alias = _group_by_alias(paths)
    for alias, items in sorted(by_alias.items()):
        if alias in ("header/struct", "header/main", "header/mobile"):
            print(f"  - alias '{alias}': {len(items)} manifest(s)")
            for (p, data) in items:
                print(f"    · {p}")
                # Indice utile : présence/absence de compose.children
                has_compose_children = bool((data.get("compose") or {}).get("children"))
                print(f"      compose.children? {has_compose_children}")

    # 3) Registre effectif
    if "header/struct" not in all_aliases():
        raise CommandError("alias 'header/struct' absent du registre — discovery invalide ou manifest manquant.")

    try:
        parent = reg_get("header/struct", namespace="core", fallback=False)
        child_main = reg_get("header/main", namespace="core", fallback=False)
        child_mobile = reg_get("header/mobile", namespace="core", fallback=False)
    except NamespaceComponentMissing as exc:
        raise CommandError(f"Composant manquant dans namespace core: {exc}")
    print("\n== Registry snapshots ==")
    _pp("registry.header/struct", parent)
    _pp("registry.header/main", child_main)
    _pp("registry.header/mobile", child_mobile)

    compose_children = (parent.get("compose") or {}).get("children") or {}
    if not compose_children:
        print("[ERROR] 'compose.children' vide sur header/struct → le parent ne connaît pas ses enfants.")
        print("        Probable cause: un MANIFEST en double sans 'compose.children' écrase le bon.")
    else:
        print(f"[OK] compose.children présent: {compose_children}")

    # 4) Validation existence templates + présence des marqueurs attendus
    print("\n== Templates & marqueurs ==")
    # parent
    parent_tpl = parent.get("template") or ""
    parent_src = _read_template_source(parent_tpl)
    print(f"parent.template={parent_tpl} exists={bool(parent_src)}")
    want_main_key = "{{ children.header_struct__main"
    want_mobile_key = "{{ children.header_struct__mobile"
    print(f"  contains '{want_main_key}': {want_main_key in parent_src}")
    print(f"  contains '{want_mobile_key}': {want_mobile_key in parent_src}")

    # enfant main
    main_tpl = child_main.get("template") if child_main else ""
    main_src = _read_template_source(main_tpl or "")
    print(f"child.main.template={main_tpl} exists={bool(main_src)}")
    has_wrapper = "header-main-wrapper" in main_src
    print(f"  contains 'header-main-wrapper': {has_wrapper}")

    # enfant mobile
    mob_tpl = child_mobile.get("template") if child_mobile else ""
    mob_src = _read_template_source(mob_tpl or "")
    print(f"child.mobile.template={mob_tpl} exists={bool(mob_src)}")
    has_mobile_id = re.search(r'id=[\'"]mobileMenu[\'"]', mob_src or "") is not None
    print(f"  contains id='mobileMenu': {has_mobile_id}")

    # 5) Rendu direct des enfants (dumps)
    request = _fake_request()
    print("\n== Render children (direct) ==")
    main_html = ""
    if main_tpl:
        try:
            main_html = render_to_string(main_tpl, {}, request=request)
            (OUTDIR / "child_main.html").write_text(main_html, encoding="utf-8")
            print(f"[OK] child main rendered → {OUTDIR / 'child_main.html'} size={len(main_html)} bytes")
        except Exception as e:
            print(f"[ERROR] render child main: {e}")

    mobile_html = ""
    if mob_tpl:
        try:
            mobile_html = render_to_string(mob_tpl, {}, request=request)
            (OUTDIR / "child_mobile.html").write_text(mobile_html, encoding="utf-8")
            print(f"[OK] child mobile rendered → {OUTDIR / 'child_mobile.html'} size={len(mobile_html)} bytes")
        except Exception as e:
            print(f"[ERROR] render child mobile: {e}")

    if main_html and "header-main-wrapper" not in main_html:
        print("[WARN] child main rendu mais sans 'header-main-wrapper' (vérifie le template).")

    if mobile_html and re.search(r'id=[\'"]mobileMenu[\'"]', mobile_html) is None:
        print("[WARN] child mobile rendu mais sans id='mobileMenu' (vérifie le template).")

    # 6) Pipeline page → slot header
    print("\n== Pipeline page slot: header ==")
    page_id = "online_home"
    ps = get_page_spec(page_id, namespace="core")
    if not ps:
        raise CommandError(f"Page '{page_id}' introuvable dans configs.")

    page_ctx = pipeline.build_page_spec(page_id, request)
    header_slot = (page_ctx.get("slots") or {}).get("header")
    if not header_slot:
        raise CommandError("Slot 'header' absent de la page.")

    _pp("slot.header", header_slot)

    # Forcer rendu sans cache pour un audit propre
    header_slot = dict(header_slot)
    header_slot["cache"] = False
    out = pipeline.render_slot_fragment(page_ctx, header_slot, request)
    html = out.get("html") or ""
    (OUTDIR / "parent_header_struct.html").write_text(html, encoding="utf-8")
    print(f"[OK] parent rendered → {OUTDIR / 'parent_header_struct.html'} size={len(html)} bytes")

    # 7) Assertions lisibles
    errors = []
    if "header-main-wrapper" not in html:
        errors.append("header/main not injected (missing 'header-main-wrapper' in parent fragment).")
    if re.search(r'id=[\'"]mobileMenu[\'"]', html) is None:
        errors.append("header/mobile not injected (missing id='mobileMenu' in parent fragment).")

    if errors:
        print("\n== VERDICT ==")
        for e in errors:
            print(f"[FAIL] {e}")
        # Aides à la correction
        print("\n== ACTIONS RECO == ")
        print("- Vérifie s’il existe plusieurs manifests pour 'header/struct' (voir la section 'manifests_on_disk').")
        print("  * Si oui: supprime l’ancien manifest (celui SANS 'compose.children').")
        print("- Confirme que 'components/header/header_struct.html' contient bien:")
        print("    {{ children.header_struct__main }} et {{ children.header_struct__mobile }}")
        print("- Confirme que 'components/header/main/header_main.html' contient 'header-main-wrapper'.")
        print("- Redémarre le serveur après nettoyage.")
        raise CommandError("Audit KO — voir détails ci-dessus.")
    else:
        print("\n== VERDICT ==")
        print("[SUCCESS] Le header parent contient ses enfants (main + mobile).")
        return
