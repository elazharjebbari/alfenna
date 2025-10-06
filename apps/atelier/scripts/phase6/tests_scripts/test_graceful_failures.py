# apps/atelier/scripts/phase6/graceful_failures.py
from apps.atelier.components.assets import collect_for
from apps.atelier.components.contracts import validate
from apps.atelier.components.registry import NamespaceComponentMissing
from apps.common.runscript_harness import binary_harness

@binary_harness
def run():
    print("=== phase6/graceful_failures ===")
    # 1) alias inconnu → collect_for doit renvoyer vide sans erreur
    try:
        collect_for(["unknown/alias"], namespace="core")
    except NamespaceComponentMissing:
        print("[OK] collect_for unknown alias -> exception NamespaceComponentMissing")
    else:
        raise AssertionError("collect_for should raise NamespaceComponentMissing")

    # 2) validate sans contrat défini (alias inconnu) -> no-op (aucune exception)
    try:
        validate("unknown/alias", {}, namespace="core")
    except NamespaceComponentMissing:
        print("[OK] validate unknown alias -> exception NamespaceComponentMissing")
    else:
        raise AssertionError("validate should raise NamespaceComponentMissing")

    print("=> PASS ✅")
