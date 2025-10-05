"""Verify chatbot components registration and assets integrity."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings

from apps.atelier.components import registry
from apps.atelier.components.assets import collect_for, order_and_dedupe, validate_assets
from apps.atelier.components.registry import NamespaceComponentMissing
from apps.common.runscript_harness import binary_harness

CHATBOT_ALIASES = [
    "chatbot/shell",
    "chatbot/panel",
    "chatbot/messages",
    "chatbot/input",
    "chatbot/consent_gate",
]


@binary_harness
def run() -> None:
    print("=== suite/tests_scripts/test_components_registry_assets_check ===")
    namespace = "core"

    missing = [alias for alias in CHATBOT_ALIASES if not registry.exists(alias, namespace=namespace, include_fallback=False)]
    assert not missing, f"Alias non enregistrés: {missing}"
    print("[OK] Aliases enregistrés")

    for alias in CHATBOT_ALIASES:
        try:
            meta = registry.get(alias, namespace=namespace, fallback=False)
        except NamespaceComponentMissing as exc:  # pragma: no cover - defensive
            raise AssertionError(f"Composant absent pour namespace core: {exc}") from exc
        template = meta.get("template")
        assert template, f"Template manquant dans le manifest pour {alias}"
        template_path = Path(settings.BASE_DIR) / "templates" / str(template)
        assert template_path.exists(), f"Template introuvable: {template_path}"
        if alias == "chatbot/shell":
            render = meta.get("render") or {}
            assert render.get("cacheable") is False, "chatbot/shell doit être render.cacheable=false"
    print("[OK] Templates présents & render.cacheable vérifié")

    assets = collect_for(CHATBOT_ALIASES, namespace=namespace)
    assets = order_and_dedupe(assets)
    validate_assets(assets)
    for kind, values in assets.items():
        assert isinstance(values, list), f"Assets[{kind}] doit être une liste"
        assert values == list(dict.fromkeys(values)), f"Doublons dans assets[{kind}]"
    print("[OK] Assets collectés & valides")
    print("=> PASS ✅")
