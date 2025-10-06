from __future__ import annotations
import os, re, sys, importlib, inspect, json
from typing import Any, Dict, Tuple, Optional

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.contrib.staticfiles import finders
from django.template.loader import get_template
from django.test import Client, RequestFactory
from django.urls import reverse, NoReverseMatch

# Compose / Atelier
from apps.atelier.compose import pipeline
from apps.atelier.components.registry import get as get_component

# Domaine
from apps.catalog.models.models import Course


B = "\033[94m"  # blue
G = "\033[92m"  # green
Y = "\033[93m"  # yellow
R = "\033[91m"  # red
X = "\033[0m"   # reset


def mask(s: str) -> str:
    if not s:
        return ""
    s = str(s)
    if len(s) <= 8:
        return "*" * len(s)
    return f"{s[:6]}…{s[-4:]}"


def hr(title: str):
    print(f"\n{B}{'='*20} {title} {'='*20}{X}")


def info(msg: str): print(f"{B}INFO{X}  {msg}")
def ok(msg: str):   print(f"{G}OK{X}    {msg}")
def warn(msg: str): print(f"{Y}WARN{X}  {msg}")
def err(msg: str):  print(f"{R}ERR{X}   {msg}")


def check_env_and_settings() -> Dict[str, Any]:
    hr("ENV & SETTINGS — STRIPE KEYS")
    keys = [
        ("STRIPE_PUBLISHABLE_KEY", settings.STRIPE_PUBLISHABLE_KEY),
        ("STRIPE_SECRET_KEY", settings.STRIPE_SECRET_KEY),
        ("STRIPE_WEBHOOK_SECRET", getattr(settings, "STRIPE_WEBHOOK_SECRET", "")),
    ]
    results = {}
    for name, val in keys:
        env_val = os.environ.get(name, None)
        print(f"- {name:>24} | env={mask(env_val) if env_val is not None else '—'} | settings={mask(val)}")
        results[name] = {"env": env_val, "settings": val}
    # Verdicts
    if not settings.STRIPE_PUBLISHABLE_KEY:
        err("STRIPE_PUBLISHABLE_KEY est VIDE côté settings — le front ne recevra aucune clé.")
    else:
        ok("STRIPE_PUBLISHABLE_KEY présent côté settings.")
    if not settings.STRIPE_SECRET_KEY:
        warn("STRIPE_SECRET_KEY vide: PaymentService passera en mode 'fake' (client_secret simulé).")
    else:
        ok("STRIPE_SECRET_KEY présent.")
    return results


def check_static_checkout_js(static_path="js/checkout.js", expected_url="/static/js/checkout.js") -> Dict[str, Any]:
    hr("STATICFILES — checkout.js")
    res = {"found": False, "fs_path": None, "url": expected_url, "served_ok": None, "content_type": None, "status": None}
    fs_path = finders.find(static_path)
    if fs_path:
        ok(f"Fichier statique trouvé: {fs_path}")
        res["found"] = True
        res["fs_path"] = fs_path
    else:
        err(f"Introuvable via staticfiles.finders: {static_path}")
    # Essai via client HTTP
    c = Client()
    r = c.get(expected_url)
    res["status"] = r.status_code
    ctype = r.headers.get("Content-Type", "")
    res["content_type"] = ctype
    if r.status_code == 200:
        if "javascript" in ctype:
            ok(f"HTTP {expected_url} => 200 ({ctype})")
            res["served_ok"] = True
        else:
            err(f"HTTP {expected_url} => 200 mais mauvais Content-Type: {ctype}")
            res["served_ok"] = False
    else:
        err(f"HTTP {expected_url} => {r.status_code}")
        res["served_ok"] = False
    return res


def _resolve_hydrator_from_manifest(manifest: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    hyd = manifest.get("hydrate") or {}
    mod = hyd.get("module")
    func = hyd.get("func")
    return mod, func


def _load_manifest_via_registry(alias: str, namespace: str) -> Dict[str, Any]:
    comp = get_component(alias, namespace=namespace)
    # Le registry normalise typiquement vers un dict avec clés 'template', 'assets', 'hydrate', 'render'...
    return comp or {}


def check_template_exists(tpl_path: str) -> bool:
    try:
        get_template(tpl_path)
        return True
    except Exception as e:
        err(f"Template introuvable: {tpl_path} ({e})")
        return False


def check_component(alias: str, namespace: str) -> Dict[str, Any]:
    hr(f"COMPONENT — {namespace}/{alias}")
    out = {"alias": alias, "namespace": namespace, "ok": False, "template_ok": False, "hydrate_sig_ok": None}
    try:
        comp = _load_manifest_via_registry(alias, namespace)
    except Exception as e:
        err(f"Registry.get a échoué pour {namespace}/{alias}: {e}")
        return out

    if not comp:
        err("Composant introuvable dans le registry.")
        return out

    ok("Composant trouvé dans le registry.")
    print(json.dumps({k: v for k, v in comp.items() if k in ("template", "assets", "hydrate", "render")}, indent=2, default=str))

    # Template
    tpl = comp.get("template")
    if tpl:
        if check_template_exists(tpl):
            ok(f"Template OK: {tpl}")
            out["template_ok"] = True
        else:
            out["template_ok"] = False
    else:
        warn("Pas de clé 'template' dans le manifest normalisé.")

    # Hydrator: module.func + signature attendue (request, params: dict)
    mod, func = _resolve_hydrator_from_manifest(comp)
    if mod and func:
        try:
            m = importlib.import_module(mod)
            f = getattr(m, func)
            sig = inspect.signature(f)
            print(f"- Signature hydrator: {f.__name__}{sig}")
            # Compose appelle: func(request, params_dict)
            # => il faut que la fonction accepte au moins 2 arguments positionnels OU *args/**kwargs qui absorbent.
            pos_count = 0
            kwonly = 0
            varpos = False
            varkw = False
            for p in sig.parameters.values():
                if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD):
                    pos_count += 1
                if p.kind == p.VAR_POSITIONAL:
                    varpos = True
                if p.kind == p.VAR_KEYWORD:
                    varkw = True
                if p.kind == p.KEYWORD_ONLY:
                    kwonly += 1
            sig_ok = (pos_count >= 2) or varpos or varkw
            if sig_ok:
                ok("Signature hydrator COMPATIBLE avec l’appel Compose (request, params_dict).")
                out["hydrate_sig_ok"] = True
            else:
                err("Signature hydrator INCOMPATIBLE: Compose passe un 2e argument POSITIONNEL (dict).")
                warn("Attendu: def hydr(req, params)  OU  def hydr(req, *args, **kwargs).")
                out["hydrate_sig_ok"] = False
        except Exception as e:
            err(f"Impossible de charger l’hydrator {mod}:{func} — {e}")
            out["hydrate_sig_ok"] = False
    else:
        warn("Aucun hydrator déclaré (module/func).")
        out["hydrate_sig_ok"] = None

    out["ok"] = bool(out["template_ok"] and (out["hydrate_sig_ok"] in (True, None)))
    return out


def build_and_render_checkout(page_id: str, slug: str, namespace: str) -> Dict[str, Any]:
    hr("BUILD & RENDER — Compose page_ctx + fragments")
    course = Course.objects.filter(slug=slug, is_published=True).first()
    if not course:
        raise CommandError(f"Course introuvable: slug={slug}")

    rf = RequestFactory()
    req = rf.get(f"/checkout/{slug}/")
    # Simuler une propriété que Compose lit parfois:
    setattr(req, "site_version", namespace)

    page_ctx = pipeline.build_page_spec(
        page_id=page_id,
        request=req,
        extra={"course": course, "currency": "EUR"},
    )
    ok(f"page_ctx construit. slots={list((page_ctx.get('slots') or {}).keys())}")

    # Assets collectés (CSS/JS)
    assets = pipeline.collect_page_assets(page_ctx)
    print("- Assets collectés:")
    print(json.dumps(assets, indent=2))

    # Rendu de chaque slot (hydrate + template)
    fragments = {}
    for sid, slot_ctx in (page_ctx.get("slots") or {}).items():
        info(f"Render slot: {sid}")
        try:
            r = pipeline.render_slot_fragment(page_ctx, slot_ctx, req)
            html = r.get("html") or ""
            fragments[sid] = html
            ok(f"Slot '{sid}' rendu: {len(html)} chars")
        except Exception as e:
            err(f"Slot '{sid}' rendu a échoué: {e}")

    return {"page_ctx": page_ctx, "assets": assets, "fragments": fragments}


def probe_checkout_http(slug: str) -> Dict[str, Any]:
    hr("HTTP GET — /checkout/<slug>/ (orchestrator)")
    c = Client()
    path = f"/checkout/{slug}/"
    r = c.get(path)
    print(f"- GET {path} => {r.status_code}")
    out = {"status": r.status_code, "has_checkout_boot": False, "stripe_pk_in_html": None}

    if r.status_code != 200:
        err("La page de checkout n’a pas renvoyé 200, le reste des tests HTML sera incomplet.")
        return out

    html = r.content.decode("utf-8", errors="ignore")
    # Cherche le boot window.__CHECKOUT__
    m = re.search(r"window\.__CHECKOUT__\s*=\s*\{([^}]+)\}", html)
    out["has_checkout_boot"] = bool(m)
    if not m:
        err("Bloc JS window.__CHECKOUT__ introuvable dans la page (boot côté form).")
    else:
        ok("Bloc JS window.__CHECKOUT__ trouvé.")
        inner = m.group(1)
        # Stripe PK (naïf): cherche stripePK: "xxxxx"
        m2 = re.search(r"stripePK\s*:\s*\"([^\"]*)\"", inner)
        if m2:
            val = m2.group(1)
            out["stripe_pk_in_html"] = val
            if val:
                ok(f"stripePK dans HTML: {mask(val)}")
            else:
                err("stripePK dans HTML est VIDE.")
        else:
            warn("Impossible d’extraire stripePK du bloc JS (syntaxe différente?).")
    return out


def check_urls():
    hr("URLS — endpoints attendus")
    # create_intent (invité)
    try:
        url = reverse("billing:create_payment_intent")
        ok(f"URL billing:create_payment_intent = {url}")
    except NoReverseMatch:
        err("URL 'billing:create_payment_intent' introuvable (namespace/urls?).")

    # (Optionnel) page orchestrator: pages:checkout si nommé — ici c’est path direct
    # On se contente du GET direct plus haut.


class Command(BaseCommand):
    help = "Diagnostique verbeux du checkout (Stripe PK, hydrators, manifests, assets, rendu Compose, HTTP)."

    def add_arguments(self, parser):
        parser.add_argument("--slug", required=True, help="Slug du cours (ex: gating-demo)")
        parser.add_argument("--page", default="checkout", help="ID de page Compose (défaut: checkout)")
        parser.add_argument("--namespace", default="core", help="Namespace de composant (défaut: core)")
        parser.add_argument("--static-js", default="js/checkout.js", help="Chemin staticfiles (défaut: js/checkout.js)")
        parser.add_argument("--static-url", default="/static/js/checkout.js", help="URL statique attendue (défaut: /static/js/checkout.js)")

    def handle(self, *args, **opts):
        slug = opts["slug"]
        page_id = opts["page"]
        namespace = opts["namespace"]
        static_js = opts["static_js"]
        static_url = opts["static_url"]

        print(f"{B}Diagnose params:{X} slug={slug} page={page_id} namespace={namespace}")

        # 1) ENV/SETTINGS
        check_env_and_settings()

        # 2) Static checkout.js
        check_static_checkout_js(static_js, static_url)

        # 3) Manifests/Components clés du checkout
        for alias in (
            "checkout/payment_form",
            "checkout/order_summary",
            "checkout/express",
            "checkout/legal_info",
        ):
            check_component(alias, namespace)

        # 4) Compose build + render (simulateur hors HTTP)
        try:
            build_and_render_checkout(page_id, slug, namespace)
        except Exception as e:
            err(f"Echec build/render Compose: {e}")

        # 5) URLs indispensables
        check_urls()

        # 6) GET HTTP réel de la page orchestrator (vérifie présence du boot window.__CHECKOUT__)
        try:
            http_res = probe_checkout_http(slug)
            # Mini verdict ciblé
            hr("VERDICT — Stripe Publishable Key dans la page")
            pk_html = http_res.get("stripe_pk_in_html")
            if http_res.get("status") == 200 and http_res.get("has_checkout_boot"):
                if pk_html:
                    ok("La clé publique Stripe est présente dans le HTML (le front pourra initialiser Stripe).")
                else:
                    err("Le HTML de la page ne contient PAS de clé publique Stripe (window.__CHECKOUT__.stripePK vide).")
                    warn("→ Causes probables: settings STRIPE_PUBLISHABLE_KEY vide OU hydrator payment_form KO.")
            else:
                err("La page n’a pas de boot window.__CHECKOUT__ — script d’initialisation non injecté.")
        except Exception as e:
            err(f"Echec GET /checkout/{slug}/ : {e}")

        hr("FIN — Consulte les sections en ERR/WARN pour corriger à la source (env, hydrators, manifest, assets).")
