# apps/flowforms/scripts/test_probe_home_form.py
from __future__ import annotations

import json
import os
import re
import sys
import textwrap
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.test import Client
from django.urls import reverse, NoReverseMatch
from apps.common.runscript_harness import binary_harness

# --- ANSI + icons ---
ANSI = {
    "G": "\033[92m",  # green
    "R": "\033[91m",  # red
    "Y": "\033[93m",  # yellow
    "B": "\033[94m",  # blue
    "C": "\033[96m",  # cyan
    "X": "\033[0m",   # reset
    "D": "\033[90m",  # dim
}
IC = {
    "ok": "✅",
    "ko": "❌",
    "warn": "⚠️",
    "info": "ℹ️",
    "magn": "🔎",
    "rocket": "🚀",
    "plug": "🔌",
    "doc": "📄",
    "pkg": "📦",
    "wrench": "🛠️",
    "eye": "👁️",
    "chain": "⛓️",
    "route": "🧭",
    "paint": "🎨",
    "chip": "🧩",
    "bolt": "⚡",
}

# --- tiny helpers ---
def ctext(txt: str, color: str) -> str:
    return f"{ANSI.get(color,'')}{txt}{ANSI['X']}"

def section(title: str) -> None:
    print(f"\n{ANSI['B']}=== {title} ==={ANSI['X']}")

def bullet(text: str, icon="•", color="X") -> None:
    print(f"  {icon} {ctext(text, color)}")

def kv(label: str, value: Any, color="X") -> None:
    print(f"    - {label}: {ctext(str(value), color)}")

@dataclass
class CheckResult:
    name: str
    ok: bool
    details: List[str] = field(default_factory=list)
    advice: List[str] = field(default_factory=list)

    def log(self) -> None:
        icon = IC["ok"] if self.ok else IC["ko"]
        color = "G" if self.ok else "R"
        print(f"{icon}  {ctext(self.name, color)}")
        for d in self.details:
            bullet(d, icon=IC["info"], color="X")
        if self.advice and not self.ok:
            for a in self.advice:
                bullet(a, icon=IC["wrench"], color="Y")


def _extract_json_config(html: str) -> Optional[Dict[str, Any]]:
    """
    Extrait le JSON embarqué du wizard inline:
      <script type="application/json" data-ff-config>{...}</script>
    """
    m = re.search(r'<script[^>]+data-ff-config[^>]*>(.*?)</script>', html, re.S | re.I)
    if not m:
        return None
    raw = (m.group(1) or "").strip()
    try:
        return json.loads(raw) if raw else {}
    except Exception:
        # parfois l’hydrateur peut injecter du JSON "tendu"; on remonte brut pour debug
        return {"__parse_error__": raw[:500]}

def _count(sel: str, html: str) -> int:
    return len(re.findall(sel, html, re.I))

def _write_snapshot(path: str, html: bytes | str) -> Optional[str]:
    try:
        if isinstance(html, bytes):
            html = html.decode("utf-8", errors="ignore")
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        return path
    except Exception:
        return None

def _divider() -> None:
    print(ctext("-" * 78, "D"))

@binary_harness
def run():
    """
    Sonde bout-à-bout la page d’accueil et le wizard inline.
    Exigences:
      - apps/pages HomeView accessible
      - composeur Atelier opérationnel
      - composant forms/shell présent dans le slot 'lead_form'
      - flowforms.runtime.js collecté dans page_assets.js
      - config FlowForms (settings.FLOWFORMS_POLICY_YAML) avec 'checkout_intent_flow'
    """
    # ----------------------------------------------------------------------
    # 0) PRE-FLIGHT
    # ----------------------------------------------------------------------
    section(f"{IC['rocket']} FlowForms Inline Probe — Home Page")
    snapshot_path = "/tmp/flowforms_home_snapshot.html"
    client = Client()

    # ENV overview
    bullet("Environnement", icon=IC["chip"])
    kv("DEBUG", getattr(settings, "DEBUG", None), "C")
    kv("LANGUAGE_CODE", getattr(settings, "LANGUAGE_CODE", "fr"), "C")
    kv("FLOWFORMS_POLICY_YAML", getattr(settings, "FLOWFORMS_POLICY_YAML", "—"), "C")

    # Sanity: apps installed
    installed = set(getattr(settings, "INSTALLED_APPS", []))
    checks: List[CheckResult] = []
    checks.append(CheckResult(
        name="Apps installées (pages, flowforms, leads)",
        ok={"apps.pages", "apps.flowforms", "apps.leads"}.issubset(installed),
        details=[f"INSTALLED_APPS contient: {', '.join(sorted(installed & {'apps.pages','apps.flowforms','apps.leads'}) or ['—'])}"],
        advice=["Vérifie INSTALLED_APPS pour 'apps.pages', 'apps.flowforms', 'apps.leads'."]
    ))

    # Flow config availability
    try:
        from apps.flowforms.conf.loader import get_flow
        flow_cfg = get_flow("checkout_intent_flow")
        ok_flow = isinstance(flow_cfg, dict) and bool(flow_cfg.get("steps"))
        step_keys = [s.get("key") for s in flow_cfg.get("steps", [])]
        checks.append(CheckResult(
            name="Config FlowForms chargée (checkout_intent_flow)",
            ok=ok_flow,
            details=[
                f"kind={flow_cfg.get('kind', '—')}",
                f"steps={len(step_keys)} ({', '.join(step_keys)})"
            ],
            advice=["Vérifie settings.FLOWFORMS_POLICY_YAML et le schéma YAML (pydantic)."]
        ))
    except Exception as e:
        checks.append(CheckResult(
            name="Config FlowForms chargée (checkout_intent_flow)",
            ok=False,
            details=[f"Exception: {e}"],
            advice=[
                "Corrige le chemin FLOWFORMS_POLICY_YAML ou la structure du YAML.",
                "Exécute: python manage.py flowforms_lint"
            ]
        ))

    # ----------------------------------------------------------------------
    # 1) GET Home page
    # ----------------------------------------------------------------------
    section(f"{IC['route']} Requête Home")
    try:
        try:
            home_url = reverse("pages:home")
        except NoReverseMatch:
            home_url = "/"
        resp = client.get(home_url, follow=True)
        status_ok = resp.status_code == 200
        html = resp.content.decode("utf-8", errors="ignore")
        snap = _write_snapshot(snapshot_path, html)
        checks.append(CheckResult(
            name="HTTP 200 sur la home",
            ok=status_ok,
            details=[f"GET {home_url} → {resp.status_code}",
                     f"Snapshot: {snap or '—'}"],
            advice=["Vérifie apps/pages/urls.py et inclusion dans urls.py racine."]
        ))
    except Exception as e:
        checks.append(CheckResult(
            name="HTTP 200 sur la home",
            ok=False,
            details=[f"Exception: {e}"],
            advice=["Investiguer la vue HomeView et la pipeline 'compose'."])
        )
        html = ""

    # ----------------------------------------------------------------------
    # 2) Analyse DOM (wizard inline)
    # ----------------------------------------------------------------------
    section(f"{IC['eye']} Inspection DOM (wizard inline)")
    if html:
        # a) slot lead_form & ff-root
        has_ff_root = 'data-ff-root' in html
        n_ff_root = _count(r'data-ff-root', html)
        n_step1 = _count(r'data-ff-step=["\']1["\']', html)
        n_step2 = _count(r'data-ff-step=["\']2["\']', html)
        n_step3 = _count(r'data-ff-step=["\']3["\']', html)
        checks.append(CheckResult(
            name="Bloc wizard présent (ff-root + steps 1/2/3)",
            ok=has_ff_root and n_step1 >= 1,
            details=[
                f"ff-root count={n_ff_root}",
                f"steps: s1={n_step1} s2={n_step2} s3={n_step3}"
            ],
            advice=[
                "Si 0: l’hydrateur du composant forms/shell n’a pas injecté l’enfant 'wizard_generic'.",
                "→ Assure-toi que forms/shell résout TOUT seul (flow_key par défaut, config_json) et que pages.yml ne fait que lier le composant."
            ]
        ))

        # b) assets JS (inclusion)
        has_runtime_tag = ('/static/js/flowforms.runtime.js' in html) or bool(
            re.search(r'<script[^>]+src=["\']/static/js/flowforms\.runtime\.js', html, re.I)
        )
        checks.append(CheckResult(
            name="Asset JS runtime inclus dans la page",
            ok=has_runtime_tag,
            details=[("Tag <script src=\"/static/js/flowforms.runtime.js\"> trouvé"
                      if has_runtime_tag else "Tag JS runtime manquant dans le HTML")],
            advice=[
                "Vérifie le manifest forms/shell.assets.js et l’agrégation pipeline.collect_page_assets.",
                "Si le formulaire apparaît sans interaction, c’est normal: le HTML est statique; le JS n’est requis que pour la navigation interne/submit."
            ]
        ))

        # c) config JSON embarquée
        cfg = _extract_json_config(html)
        ok_cfg = isinstance(cfg, dict)
        flow_key_in_cfg = (cfg or {}).get("flow_key") if ok_cfg else None
        endpoint_url = (cfg or {}).get("endpoint_url") if ok_cfg else None
        parse_err = "__parse_error__" in (cfg or {})
        details = []
        if parse_err:
            details.append("Erreur de parsing JSON embarqué (dump tronqué ci-dessous)")
            details.append((cfg or {}).get("__parse_error__", "")[:200])
        else:
            details.append(f"flow_key={flow_key_in_cfg or '—'}")
            details.append(f"endpoint_url={endpoint_url or '—'}")
        checks.append(CheckResult(
            name="Config JSON embarquée (data-ff-config)",
            ok=ok_cfg and not parse_err,
            details=details,
            advice=[
                "L’hydrateur forms_shell doit fournir un JSON propre (flow_key, form_kind, endpoint_url, ui…).",
                "Sans config JSON, l’affichage Step 1 reste possible, mais la soumission échouera."
            ]
        ))

        # d) heuristique display inline vs modal
        inline_detected = 'id="ff-shell-' in html or 'data-ff-step="1"' in html
        checks.append(CheckResult(
            name="Rendu en display=inline (pas modal)",
            ok=inline_detected,
            details=["Heuristique: présence du container inline et des steps visibles dans le flux HTML."],
            advice=["Si tu vises l’inline, force display='inline' côté params/hydrateur."]
        ))

    # ----------------------------------------------------------------------
    # 3) Wizard serveur (endpoint /flowforms/<flow_key>/) — contrôle de santé
    # ----------------------------------------------------------------------
    section(f"{IC['plug']} Vérification wizard serveur")
    try:
        wizard_url = reverse("flowforms:wizard", kwargs={"flow_key": "checkout_intent_flow"})
    except NoReverseMatch:
        wizard_url = "/flowforms/checkout_intent_flow/"
    try:
        r = client.get(wizard_url, follow=True)
        ok = (200 <= r.status_code < 400) and (b"FlowForms" in r.content or b"id=\"flowforms-sentinel\"" in r.content)
        checks.append(CheckResult(
            name="Endpoint wizard /flowforms/checkout_intent_flow/ opérationnel",
            ok=ok,
            details=[f"GET {wizard_url} → {r.status_code}",
                     ("Sentinel présent" if (b"flowforms" in r.content.lower()) else "Sentinel absent")],
            advice=["Si KO: vérifie URLs flowforms, config YAML valide, et templates 'flowforms/wizard_form.html'."]
        ))
    except Exception as e:
        checks.append(CheckResult(
            name="Endpoint wizard /flowforms/checkout_intent_flow/ opérationnel",
            ok=False,
            details=[f"Exception: {e}"],
            advice=["Corriger résolution d’URL ou erreurs runtime du wizard serveur."]
        ))

    # ----------------------------------------------------------------------
    # 4) LOGS + DIAGNOSTIC FINAL
    # ----------------------------------------------------------------------
    section(f"{IC['magn']} Résultats des contrôles")
    for res in checks:
        res.log()

    _divider()
    all_ok = all(c.ok for c in checks)
    if all_ok:
        print(f"{IC['ok']} {ctext('Tous les contrôles sont OK.', 'G')}")
    else:
        print(f"{IC['warn']} {ctext('Des anomalies ont été détectées.', 'Y')}")

    # Diagnostic plus précis: cause la plus fréquente du “formulaire invisible”
    cause = None
    # 1) Pas de ff-root → child non injecté
    cr_ff = next((c for c in checks if "Bloc wizard présent" in c.name), None)
    if cr_ff and not cr_ff.ok:
        cause = textwrap.dedent(f"""
        {IC['wrench']} Hypothèse racine: l'hydrateur du composant **forms/shell** n'a pas injecté le child `forms/wizard_generic`.
            • Le `manifest` de forms/shell déclare `flow_key` comme requis : s'il n'est pas fourni et que l'hydrateur ne fixe pas de **valeur par défaut**, la composition peut omettre l'enfant.
            • Aligne avec ton exigence (toute la config dans le composant) : fais résoudre `flow_key`, `endpoint_url`, `form_kind`, `ui_texts` côté **hydrateur**, et laisse `pages.yml` ne faire que **lier** le composant.
        """).strip()

    # 2) Asset runtime non inclus
    cr_js = next((c for c in checks if "Asset JS runtime" in c.name), None)
    if not cause and cr_js and not cr_js.ok:
        cause = f"{IC['wrench']} L'asset JS runtime n'est pas inclus. Le HTML peut s'afficher, mais l'interaction (navigation/submit) ne fonctionnera pas."

    # 3) JSON embarqué invalide
    cr_cfg = next((c for c in checks if "Config JSON embarquée" in c.name), None)
    if not cause and cr_cfg and not cr_cfg.ok:
        cause = f"{IC['wrench']} Le JSON embarqué (data-ff-config) est invalide. Vérifie le sérialiseur de l'hydrateur pour produire un JSON strict."

    if cause:
        _divider()
        print(cause)

    _divider()
    print(f"{IC['doc']} Snapshot HTML: {snapshot_path if os.path.exists(snapshot_path) else '—'}")
    print(f"{IC['bolt']} Fin du test.")
