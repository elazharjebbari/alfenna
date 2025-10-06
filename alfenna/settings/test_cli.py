# alfenna/settings/test_cli.py
from .dev import *  # noqa: F401,F403

# Cache local en mémoire
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "cli-tests",
        "TIMEOUT": 300,
    }
}

# Celery: exécution synchrone (pas de broker)
# Si tu utilises Celery >=4 : task_always_eager
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
# Pour compatibilité de result backend en mémoire
CELERY_RESULT_BACKEND = "cache+memory://"

# Channels: couche en mémoire (si Channels est installé)
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer"
    }
}

# Éventuels flags project-specific utiles pour tests CLI
FLOWFORMS_COMPONENT_ENABLED = True
# Désactiver features coûteuses si besoin:
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Force Stripe into offline mode during CLI smoke/tests to avoid hitting the API.
STRIPE_SECRET_KEY = ""
STRIPE_WEBHOOK_SECRET = ""

INVOICING_ENABLED = False

WHITENOISE_AUTOREFRESH = True
WHITENOISE_USE_FINDERS = False

# Google Ads S2S harness defaults to mock uploads during CLI tests.
ADS_S2S_MODE = "mock"

# Playwright analytics suite disabled on CLI runs to keep tests lightweight.
ENABLE_PLAYWRIGHT_TESTS = False

# Ensure chatbot slot remains active during CLI tests.
CHATBOT_ENABLED = True

# Allow context to be ignored temporarily when verifying signatures during CLI tests.
LEADS_SIGNATURE_IGNORE_FIELDS = ["context"]
