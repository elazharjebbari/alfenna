# scripts/core_settings_check.py
from django.conf import settings
from django.core.management import call_command

def run(*args):
    print("== core_settings_check: début ==")

    # SECRET_KEY
    assert bool(settings.SECRET_KEY), "SECRET_KEY manquant"

    # Position de WhiteNoise
    mw = settings.MIDDLEWARE
    sec_idx = mw.index('django.middleware.security.SecurityMiddleware')
    white_idx = mw.index('whitenoise.middleware.WhiteNoiseMiddleware')
    assert white_idx == sec_idx + 1, "WhiteNoise doit suivre SecurityMiddleware"

    # Static storage
    sf = settings.STORAGES.get('staticfiles', {})
    assert sf.get('BACKEND') == 'whitenoise.storage.CompressedManifestStaticFilesStorage', \
        "STORAGES.staticfiles doit utiliser CompressedManifestStaticFilesStorage"

    if not settings.DEBUG:
        # Flags prod obligatoires
        assert settings.SESSION_COOKIE_SECURE, "SESSION_COOKIE_SECURE doit être True en prod"
        assert settings.CSRF_COOKIE_SECURE, "CSRF_COOKIE_SECURE doit être True en prod"
        assert settings.SECURE_SSL_REDIRECT, "SECURE_SSL_REDIRECT doit être True en prod"
        assert settings.SECURE_HSTS_SECONDS and settings.SECURE_HSTS_SECONDS >= 31536000, \
            "HSTS trop faible ou absent"
        assert settings.ALLOWED_HOSTS and '*' not in settings.ALLOWED_HOSTS, \
            "ALLOWED_HOSTS invalide en prod"
        assert isinstance(settings.CSRF_TRUSTED_ORIGINS, (list, tuple)) and len(settings.CSRF_TRUSTED_ORIGINS) > 0, \
            "CSRF_TRUSTED_ORIGINS vide en prod"

    # Django deploy checks
    call_command('check', '--deploy')

    print("== core_settings_check: OK ✅ ==")
