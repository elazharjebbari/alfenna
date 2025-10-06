"""
Vérifie que la politique TTL du YAML est bien lue et appliquée par ttl_for.
Exécution: python manage.py runscript phase7.ttl_policy_check
"""
from apps.atelier.compose.cache import ttl_for
from apps.common.runscript_harness import binary_harness

@binary_harness
def run():
    print("=== phase7/ttl_policy_check ===")
    # Valeurs issues de ta config cache.yml
    assert ttl_for("hero") == 2700, "TTL attendu pour slot 'hero' = 2700"
    # TTL par alias si slot non trouvé
    assert ttl_for("unknown-slot", "footer/main") == 604800, "TTL attendu pour alias 'footer/main' = 604800"
    # Clamp >= 1
    assert ttl_for("header/struct") >= 1, "TTL doit être clampé à >=1 même si YAML=0"
    print("=> PASS ✅")