# alfenna/settings/dev.py
# export DJANGO_SETTINGS_MODULE=alfenna.settings.dev

from .base import *

DEBUG = True

ALLOWED_HOSTS = ['127.0.0.1',
                 'localhost',
                 'testserver',
                 ".ngrok.io", ".ngrok-free.app",  # ngrok v2/v3
                 "alfenna.com", "lumiereacademy.com", 'testserver'
                 ]
CSRF_TRUSTED_ORIGINS = [
    'http://127.0.0.1:8000', 'http://localhost:8000',
    "https://*.ngrok.io", "https://*.ngrok-free.app",
    'http://*'
]

CORS_ALLOWED_ORIGINS = [
    # ajoute tes domaines front ici
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://127.0.0.1:3000",
]
CORS_ALLOW_CREDENTIALS = True

# Dev: pas de redirection SSL forcée
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False


# Emails en console si tu préfères debug facile
if os.getenv('DEV_EMAIL_CONSOLE', '1') in ('1', 'true', 'True'):
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# SQLite par défaut en dev (déjà configuré dans base)

LOGGING['loggers'].update({
    'atelier.header.debug': {
        'handlers': ['console'],
        'level': 'WARNING',
        'propagate': False,
    },
})

COMPRESS_ENABLED = True
COMPRESS_OFFLINE = False

# Dev: permettre la recherche disque pour les bundles
WHITENOISE_AUTOREFRESH = True
WHITENOISE_USE_FINDERS = True

# LEADS_SIGNATURE_IGNORE_FIELDS = ["context"]