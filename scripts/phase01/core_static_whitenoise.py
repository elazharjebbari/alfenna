# scripts/core_static_whitenoise.py
from django.conf import settings
from pathlib import Path

def run(*args):
    print("== core_static_whitenoise: début ==")

    assert settings.STATIC_URL, "STATIC_URL vide"
    static_root = Path(settings.STATIC_ROOT)
    assert static_root.is_absolute(), "STATIC_ROOT doit être un chemin absolu"
    # On n'exige pas l'existence ici; collectstatic la créera en CI/CD

    mw = settings.MIDDLEWARE
    sec_idx = mw.index('django.middleware.security.SecurityMiddleware')
    white_idx = mw.index('whitenoise.middleware.WhiteNoiseMiddleware')
    assert white_idx == sec_idx + 1, "WhiteNoise doit suivre SecurityMiddleware"

    print("== core_static_whitenoise: OK ✅ ==")
