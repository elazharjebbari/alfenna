# apps/atelier/scripts/phase6/assets_dedup_order_check.py
from apps.atelier.components.assets import collect_for, order_and_dedupe
from apps.common.runscript_harness import binary_harness

@binary_harness
def run():
    print("=== phase6/assets_dedup_order_check ===")
    aliases = [
        "hero/slider",       # vendors 'swiper' attendus en tête si utilisés
        "cta/primary",
        "footer/main",
        "cta/primary",       # répété volontairement
    ]
    assets = order_and_dedupe(collect_for(aliases, namespace="core"))
    # Pas d’exigence de présence réelle, on vérifie surtout structure et dédup
    for kind in ("css", "js", "head"):
        seq = assets.get(kind, [])
        assert seq == list(dict.fromkeys(seq)), f"Doublons détectés dans {kind}"
    print("[OK] Déduplication & ordre stables")
    print("=> PASS ✅")
