"""
Smoke test: vérifie la génération de variantes pour une image statique.
- Suppose qu'au moins une image 'images/hero.jpg' existe dans STATICFILES_DIRS.
- Lance collectstatic avant si nécessaire.
"""
from __future__ import annotations
import os
from pathlib import Path
from django.conf import settings
from django.contrib.staticfiles import finders, storage
from apps.common.runscript_harness import binary_harness

@binary_harness
def run():
    print("=== variants_smoke ===")
    # 1) Trouver une image candidate
    candidate = None
    for rel in ["images/about.jpg", "img/hero.jpg", "images/sample.jpg"]:
        p = finders.find(rel)
        if p:
            candidate = rel
            break
    if not candidate:
        print("[SKIP] aucune image candidate trouvée dans STATICFILES_DIRS (ex: images/hero.jpg)")
        return

    st = storage.staticfiles_storage
    # 2) Résoudre URL pour forcer la prise en compte du manifest
    try:
        url = st.url(candidate)
        print(f"[INFO] url={url}")
    except Exception as e:
        print(f"[FAIL] static url resolve: {e}")
        return

    # 3) Lire la map des variantes
    idx = getattr(st, "variants_index", {})
    entry = idx.get(candidate)
    if not entry:
        print("[WARN] Aucune variante trouvée dans manifest — as-tu lancé collectstatic ?")
        return

    print("[OK] Variantes présentes:")
    for fmt, rel in entry.items():
        print(f"  - {fmt}: {rel}")

    sample_keys = [
        "images/shape/shape-8.png",
        "images/slider/slider-default.png",
    ]
    for key in sample_keys:
        entry = idx.get(key)
        if entry:
            print(f"[INFO] {key} -> {sorted(entry)}")
        else:
            print(f"[WARN] {key} absent de variants_index")
    print("=> PASS ✅")
