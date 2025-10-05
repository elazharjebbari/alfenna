from django.template.loader import get_template
from apps.atelier.components import registry
from apps.common.runscript_harness import binary_harness

@binary_harness
def run():
    print("=== components/discovery_smoke ===")
    aliases = registry.all_aliases()
    assert isinstance(aliases, list)
    if not aliases:
        print("[WARN] Aucun alias découvert.")
    else:
        print(f"[OK] {len(aliases)} alias découverts")
    # Vérifie que chaque template est résoluble
    for a in aliases:
        tpl = registry.get(a).get("template")
        try:
            get_template(tpl)
        except Exception as e:
            raise AssertionError(f"Template introuvable pour {a}: {tpl} ({e})")
    print("=> PASS ✅")
