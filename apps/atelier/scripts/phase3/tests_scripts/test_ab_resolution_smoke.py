# apps/atelier/scripts/phase3/ab_resolution_smoke.py
"""
Teste la résolution de variante pour hero_v2 sur 100 itérations.
Exécution: python manage.py runscript phase3.ab_resolution_smoke
"""
from django.test.client import RequestFactory
from django.contrib.auth.models import AnonymousUser

from apps.atelier.config.loader import get_page_spec
from apps.atelier.ab import waffle
from apps.common.runscript_harness import binary_harness


@binary_harness
def run():
    print("=== ab_resolution_smoke ===")

    # Récupère les variants depuis la config pages.yml (normalisée par le loader)
    spec = get_page_spec("online_home") or {}
    hero_spec = (spec.get("slots") or {}).get("hero") or {}
    variants = hero_spec.get("variants") or {}

    # Sanity checks
    assert isinstance(variants, dict) and variants, "Aucun variants défini pour online_home.hero"

    rf = RequestFactory()
    counts = {"A": 0, "B": 0, "OTHER": 0}

    for _ in range(100):
        req = rf.get("/")
        req.user = AnonymousUser()
        vkey, _alias = waffle.resolve_variant("hero_v2", variants, req)
        if vkey in ("A", "B"):
            counts[vkey] += 1
        else:
            counts["OTHER"] += 1

    print("Répartition:", counts)
    # Notre implémentation P0 renvoie toujours "A" si présent → on vérifie juste que A > 0.
    assert counts["A"] > 0, "A jamais choisi (anormal)"
    # B peut être 0 avec la résolution P0; c’est attendu.
    print("=> A/B resolution smoke OK ✅ (B facultatif en P0)")
