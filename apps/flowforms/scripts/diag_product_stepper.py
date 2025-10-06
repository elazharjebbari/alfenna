# apps/flowforms/scripts/diag_product_stepper.py
from __future__ import annotations
import json, re, shlex
from urllib.parse import urlparse
from bs4 import BeautifulSoup  # pip install beautifulsoup4
from django.urls import reverse, NoReverseMatch
from django.test import Client
from apps.common.runscript_harness import binary_harness

def _rev(name: str, default: str):
    try:
        return reverse(name)
    except NoReverseMatch:
        return default

def _parse_script_args(raw) -> dict:
    tokens: list[str] = []
    if isinstance(raw, str):
        tokens = shlex.split(raw)
    elif isinstance(raw, (list, tuple)):
        for item in raw:
            if isinstance(item, str):
                tokens.extend(shlex.split(item))
    out = {}
    for tok in tokens:
        if "=" in tok:
            k, v = tok.split("=", 1)
            out[k.strip()] = v.strip()
    return out

@binary_harness
def run(*args, **kwargs):
    # ---------------- Parse & defaults ----------------
    kv = _parse_script_args(kwargs.get("script_args") or args or [])
    url = kv.get("url", "/produits/")  # <-- défaut : /produits/
    slug = kv.get("slug", "").strip("/")
    use_slug = (kv.get("use_slug", "false").lower() in ("1", "true", "yes"))

    # Autorise URL absolue, on ne garde que le path pour le Client Django
    if url.startswith(("http://","https://")):
        url = urlparse(url).path or "/"

    # Join slug uniquement si explicitement demandé
    if use_slug and slug:
        if not url.endswith("/"):
            url += "/"
        url = url + slug

    print(f"[STEP] testing path: {url} (use_slug={use_slug})")

    c = Client()
    r = c.get(url, follow=True)
    out = {"ok": r.status_code==200, "status": r.status_code, "checks": [], "url": url}
    if r.status_code != 200:
        print(f"[ERR] HTTP {r.status_code} sur {url}")
        return {"ok": False, "name": "diag_product_stepper", "logs": [out]}

    # ---------------- Analyse HTML ----------------
    html = r.content.decode("utf-8", errors="ignore")
    soup = BeautifulSoup(html, "html.parser")

    # 1) Composant produit présent ?
    has_product = bool(soup.select_one('[data-cmp="product"]'))
    out["checks"].append({"product_component": has_product})
    if not has_product:
        print("[ERR] Composant produit introuvable (data-cmp='product').")

    # 2) Stepper local ou shell FlowForms ?
    form_root = soup.select_one("[data-form-stepper]") or soup.select_one("[data-ff-root]")
    out["checks"].append({"form_present": form_root is not None})
    if form_root is None:
        print("[ERR] Aucun stepper détecté (ni data-form-stepper ni data-ff-root).")

    # 3) Config FlowForms embarquée ?
    cfg_script = soup.select_one("script[data-ff-config]")
    out["checks"].append({"ff_config_found": cfg_script is not None})
    if cfg_script is None:
        print("[WARN] Pas de <script data-ff-config> (si tu utilises FlowForms shell).")

    # 4) Template d'inclusion résolu ?
    inc_hint = "Ce formulaire necessite une configuration"
    include_ok = (inc_hint not in html)
    out["checks"].append({"include_form_template_resolved": include_ok})
    if not include_ok:
        print("[ERR] form.template NON résolu (le placeholder 'Ce formulaire necessite une configuration.' est présent).")

    # 5) Endpoints sign/collect résolus dans Django
    sign_url = _rev("leads:sign", "/api/leads/sign/")
    collect_url = _rev("leads:collect", "/api/leads/collect/")
    out["checks"].append({"sign_url": sign_url, "collect_url": collect_url})
    print(f"[OK ] API leads: sign={sign_url} collect={collect_url}")

    # 6) Pattern /.../v repéré ?
    bad_v = re.search(r"pattern\s*=\s*\"/.+?/v\"", html)
    out["checks"].append({"bad_regex_v_flag_detected": bool(bad_v)})
    if bad_v:
        print("[ERR] pattern HTML avec flag /v détecté. Corrige le JS qui compile le pattern ou remplace par un pattern sans /.../v.")

    # 7) JS attendu
    has_lead_stepper = ("lead_stepper.js" in html)
    has_flowforms_rt = ("flowforms.runtime.js" in html)
    out["checks"].append({"lead_stepper_js": has_lead_stepper, "flowforms_runtime_js": has_flowforms_rt})
    if not (has_lead_stepper or has_flowforms_rt):
        print("[ERR] Aucune runtime JS de formulaire détectée (ni lead_stepper.js ni flowforms.runtime.js).")

    # Résumé
    errors = []
    if not has_product: errors.append("product component absent")
    if form_root is None: errors.append("stepper/shell absent")
    if not include_ok: errors.append("form.template non résolu")
    if bad_v: errors.append("pattern /.../v détecté dans le HTML")
    out["errors"] = errors
    ok = out["ok"] and not errors
    if not ok:
        print("[SUM] KO →", ", ".join(errors) if errors else "raison inconnue")
    else:
        print("[SUM] OK → composant + stepper détectés, form inclus, endpoints résolus.")
    return {"ok": ok, "name": "diag_product_stepper", "logs": [out]}
