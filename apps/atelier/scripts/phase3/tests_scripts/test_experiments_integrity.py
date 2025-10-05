"""
Valide la présence des pages/slots attendus et du flag hero_v2 (A/B).
Exécution: python manage.py runscript experiments_integrity
"""
from apps.atelier.config import registry as cfg
from apps.common.runscript_harness import binary_harness

@binary_harness
def run():
    print("=== experiments_integrity ===")
    pages = cfg.pages()
    exps = cfg.experiments()

    assert "online_home" in pages, "Page 'online_home' absente de la config"
    home = pages["online_home"]
    assert "slots" in home, "online_home.slots manquant"
    assert "hero" in home["slots"], "Slot 'hero' manquant sur online_home"

    print("\n"*3)
    print(home)
    print("\n"*3)

    # Le slot hero doit définir au moins 1 variant, idéalement A/B
    hero = home["slots"]["hero"]
    variants = hero.get("variants") or {}
    assert variants, "Aucune variante définie pour hero"
    assert set(variants.keys()) >= {"A"}, "Variante A absente sur hero"
    # On vérifie la présence éventuelle de B si A/B actif
    if "B" in variants:
        print("OK: variantes A et B présentes pour hero")
    else:
        print("WARN: variante B absente; seul A actif")

    # Flag A/B
    assert "hero_v2" in exps, "Flag A/B 'hero_v2' absent"
    print("=> Pages & expériences OK ✅")