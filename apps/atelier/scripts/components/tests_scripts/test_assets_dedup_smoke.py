from apps.atelier.components.assets import collect_for, order_and_dedupe
from apps.atelier.components import registry
from apps.common.runscript_harness import binary_harness

@binary_harness
def run():
    print("=== components/assets_dedup_smoke ===")
    aliases = registry.all_aliases()[:5]  # échantillon
    assets = order_and_dedupe(collect_for(aliases, namespace="core"))
    css, js = assets.get("css", []), assets.get("js", [])
    # Basic checks
    assert len(css) == len(set(css)), "Doublons CSS détectés"
    assert len(js) == len(set(js)), "Doublons JS détectés"
    print(f"[OK] assets collectés (CSS={len(css)}, JS={len(js)}), aucun doublon.")
    print("=> PASS ✅")
