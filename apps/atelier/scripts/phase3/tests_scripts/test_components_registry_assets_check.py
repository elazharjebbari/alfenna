"""
Vérifie que les alias enregistrés pointent vers des templates existants et que
la collecte d'assets déduplique bien CSS/JS.
Exécution: python manage.py runscript components_registry_assets_check
"""
from pathlib import Path
from django.conf import settings
from apps.atelier.components import registry
from apps.atelier.components.registry import NamespaceComponentMissing
from apps.atelier.components.assets import collect_for, order_and_dedupe
from apps.common.runscript_harness import binary_harness

# Liste d'aliases critiques attendus en P0 (à ajuster selon ton registry réel)
REQUIRED_ALIASES = [
    "header/struct",
    "hero/cover",
    "hero/slider",
    "cta/primary",
    "proofbar/videos",
    "footer/main",
    "contact/phone",
]

@binary_harness
def run():
    print("=== components_registry_assets_check ===")
    missing_aliases = [a for a in REQUIRED_ALIASES if not registry.exists(a, namespace="core", include_fallback=False)]
    if missing_aliases:
        print("KO: alias non enregistrés:", missing_aliases)
    else:
        print("OK: tous les alias requis sont enregistrés")

    # Vérifie l'existence des templates sur disque
    missing_templates = []
    for a in REQUIRED_ALIASES:
        try:
            meta = registry.get(a, namespace="core", fallback=False)
        except NamespaceComponentMissing:
            missing_templates.append((a, "namespace core: composant absent"))
            continue
        tpath = meta.get("template")
        if not tpath:
            missing_templates.append((a, "template non défini"))
            continue
        # chemin relatif aux templates/
        full = Path(settings.BASE_DIR) / "templates" / tpath
        if not full.exists():
            missing_templates.append((a, f"template introuvable: {full}"))
        else:
            print(f"[OK] {a} → {full}")

    assert not missing_templates, f"Templates manquants: {missing_templates}"

    # Déduplication d'assets
    assets = collect_for(REQUIRED_ALIASES, namespace="core")
    deduped = order_and_dedupe(assets)
    for kind in ("css", "js", "head"):
        seq = deduped.get(kind, [])
        unique = list(dict.fromkeys(seq))
        assert seq == unique, f"Doublons détectés dans {kind}"
        print(f"Assets {kind}: {len(seq)} items (dédupliqués)")

    print("=> Registry/Assets OK ✅")
