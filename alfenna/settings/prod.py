# alfenna/settings/prod.py
from .base import *

DEBUG = False

COMPRESS_ENABLED = True
COMPRESS_OFFLINE = True

SEO_ENV = "prod"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME", "alfenna_db"),
        "USER": os.getenv("DB_USER", "user_alfenna"),
        "PASSWORD": os.getenv("DB_PASSWORD"),
        "HOST": os.getenv("DB_HOST", "127.0.0.1"),  # "" pour socket Unix
        "PORT": os.getenv("DB_PORT", "5432"),
        "CONN_MAX_AGE": int(os.getenv("DB_CONN_MAX_AGE", "60")),  # pooling Django
    }
}

# Domaine(s) à fournir via env
SITE_DOMAIN = os.getenv('SITE_DOMAIN')  # ex: "cours.example.com"
SITE_ALIASES = os.getenv("SITE_ALIASES", "")  # ex: "www.lumiereacademy.com,foo.example.com"
if not SITE_DOMAIN:
    raise RuntimeError("SITE_DOMAIN n'est pas défini en production.")

ALIASES = [h.strip() for h in SITE_ALIASES.split(",") if h.strip()]
ALLOWED_HOSTS = [SITE_DOMAIN, "127.0.0.1", 'testserver'] +  ALIASES
CSRF_TRUSTED_ORIGINS =  (
    [f"https://{SITE_DOMAIN}"] +
    [f"https://{h}" for h in ALIASES] +
    ["http://localhost:8000", "http://127.0.0.1:8000", "http://127.0.0.1:8003", "http://127.0.0.1:9013"]
)

# DB: refuse sqlite en prod
if DATABASES['default']['ENGINE'].endswith('sqlite3'):
    raise RuntimeError("SQLite est interdit en production. Configure DB_ENGINE/DB_NAME/...")

# Sécurité déjà forte dans base; on peut renforcer si besoin
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

# Log niveau INFO/ERROR
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOGGING['root']['level'] = LOG_LEVEL
LOGGING['loggers']['django.request']['level'] = 'ERROR'

CORS_ALLOWED_ORIGINS = [
    # ajoute tes domaines front ici
    "http://localhost:8003",
    "http://127.0.0.1:8003",
    "http://127.0.0.1:9013",
]

CORS_ALLOW_CREDENTIALS = True

# Activer temporairement les en-têtes de debug consentement pour la recette prod.
CONSENT_DEBUG_HEADERS = True

# Aligner le nom du cookie marketing côté serveur (TAC ↔ backend ↔ JS)
CONSENT_COOKIE_NAME = "cookie_consent_marketing"

# En prod, l'email doit être opérationnel dès le boot
EMAIL_PREFLIGHT_REQUIRED = True
EMAIL_BACKEND_ENFORCE_SMTP = True
