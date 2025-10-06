from __future__ import annotations
import time
from pathlib import Path

from django.conf import settings
from pydantic import ValidationError

from apps.atelier.components.forms.shell.contracts import (
    ShellContractV3,
)
from apps.common.runscript_harness import binary_harness


def _find_manifest():
    candidates = [
        settings.BASE_DIR / "templates" / "components" / "forms" / "manifest",
        settings.BASE_DIR / "alfenna" / "templates" / "components" / "forms" / "manifest",
        settings.BASE_DIR / "apps" / "atelier" / "templates" / "components" / "forms" / "manifest",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None

@binary_harness
def run():
    t0 = time.time()
    logs = []
    ok = True

    # 1) Cas valide — child complet
    try:
        c = ShellContractV3(
            display="inline",
            title_html="Titre",
            subtitle_html="Sous-titre",
            child={
                "flow_key": "checkout_intent_flow",
                "config_json": '{"flow_key":"checkout_intent_flow","endpoint_url":"/api/leads/collect/"}',
                "backend_config": {
                    "endpoint_url": "/api/leads/collect/",
                    "require_signed_token": False,
                },
                "ui_texts": {"next": "Suivant"},
            },
        )
        assert c.child is not None and c.child.flow_key == "checkout_intent_flow"
        logs.append("✅ Contrat V3 valide avec `child`")
    except ValidationError as e:
        ok = False
        logs.append(f"❌ Validation échouée sur cas valide: {e}")

    # 2) Cas invalide — champ non whitelisté dans child
    try:
        ShellContractV3(
            child={
                "flow_key": "ff",
                "config_json": "{}",
                "unknown": "boom",  # ← doit être rejeté
            }
        )
        ok = False
        logs.append("❌ Un champ non whitelisté n'a pas été rejeté")
    except ValidationError:
        logs.append("✅ Champ non whitelisté correctement rejeté")

    # 3) Compat — wizard_ctx déprécié mappé vers child
    try:
        c2 = ShellContractV3(
            wizard_ctx={"flow_key": "legacy_flow", "config_json": "{}"}
        )
        assert c2.child is not None and c2.child.flow_key == "legacy_flow"
        logs.append("✅ `wizard_ctx` mappé vers `child` (compat OK)")
    except ValidationError as e:
        ok = False
        logs.append(f"❌ Compat wizard_ctx → child a échoué: {e}")

    manifest = _find_manifest()
    if not manifest:
        ok = False
        logs.append("❌ Manifest forms/shell introuvable (essayé racine, package, app)")
    else:
        text = manifest.read_text(encoding="utf-8")
        has_contract = "contract:" in text
        has_child = "child:" in text
        has_wizard_ctx = "wizard_ctx:" in text
        if has_contract and has_child and has_wizard_ctx:
            logs.append(f"✅ Manifest documente `child` et `wizard_ctx` — {manifest}")
        else:
            ok = False
            logs.append(f"❌ Manifest trouvé ({manifest}) mais clés manquantes (contract/child/wizard_ctx)")

    return {
        "name": "Étape 1 — Contrat parent V3",
        "ok": ok,
        "duration": round(time.time() - t0, 2),
        "logs": logs,
    }
