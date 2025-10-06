# apps/atelier/scripts/phase6/components_registry_assets_check.py
from pathlib import Path
from django.conf import settings
from apps.atelier.components import registry
from apps.atelier.components.assets import collect_for, order_and_dedupe, validate_assets
from apps.atelier.components.registry import NamespaceComponentMissing
from apps.common.runscript_harness import binary_harness

REQUIRED_ALIASES = [
    "header/struct",
    "hero/cover",
    "hero/slider",
    "proofbar/videos",
    "cta/primary",
    "footer/main",
    "contact/phone",
]

@binary_harness
def run():
    print("=== phase6/components_registry_assets_check ===")
    # 1) alias enregistrés
    missing = [a for a in REQUIRED_ALIASES if not registry.exists(a, namespace="core", include_fallback=False)]
    assert not missing, f"Alias non enregistrés: {missing}"
    print("[OK] Aliases enregistrés")

    # 2) templates existent (chemin relatif à templates/)
    for a in REQUIRED_ALIASES:
        try:
            meta = registry.get(a, namespace="core", fallback=False)
        except NamespaceComponentMissing as exc:
            raise AssertionError(f"Composant absent pour namespace core: {exc}")
        t = meta.get("template")
        full = Path(settings.BASE_DIR) / "templates" / str(t)
        assert full.exists(), f"Template introuvable pour {a}: {full}"
    print("[OK] Templates présents sur disque")

    # 3) assets: collecte dédupliquée, structure valide
    assets = collect_for(REQUIRED_ALIASES, namespace="core")
    assets = order_and_dedupe(assets)
    validate_assets(assets)
    for kind in ("css", "js", "head"):
        seq = assets.get(kind, [])
        assert isinstance(seq, list), f"Assets[{kind}] doit être une list"
        assert seq == list(dict.fromkeys(seq)), f"Doublons détectés dans {kind}"
    print("[OK] Assets collectés & dédupliqués")
    print("=> PASS ✅")
