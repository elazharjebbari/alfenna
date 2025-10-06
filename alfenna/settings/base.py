# alfenna/settings/base.py
from __future__ import annotations
import os
from pathlib import Path
from typing import Any

from celery.schedules import crontab

# Optionnel en dev, inerte si .env absent
try:
    from dotenv import load_dotenv, find_dotenv  # type: ignore

    _dotenv_path = find_dotenv(filename=os.getenv("DOTENV_FILE", ".env"), usecwd=True)
    if _dotenv_path:
        load_dotenv(_dotenv_path, override=False)
    else:
        # Aucun fichier .env trouvé; laisser l'environnement tel quel.
        pass
except Exception:
    pass

BASE_DIR = Path(__file__).resolve().parents[2]  # .../alfenna

_TRUE_VALUES = {"1", "true", "yes", "y", "on"}


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return bool(default)
    return str(value).strip().lower() in _TRUE_VALUES


def _env_flag(name: str, *, default: bool = False) -> bool:
    """Read a boolean environment variable with tolerant parsing."""
    return env_flag(name, default=default)


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return int(default)


# --------------------------------------------------------------------------------------
# Clés & debug
# --------------------------------------------------------------------------------------
SECRET_KEY = os.getenv('SECRET_KEY', 'CHANGE_ME_DEV_ONLY')
DEBUG = False  # Par défaut: sécurisé. Dev.py le passera à True.

ALLOWED_HOSTS: list[str] = ["alfenna.com", "lumiereacademy.com"]
CSRF_TRUSTED_ORIGINS = ["https://alfenna.com"]
# --------------------------------------------------------------------------------------
# Apps
# --------------------------------------------------------------------------------------
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sitemaps',
    'django.contrib.humanize',
]

THIRD_PARTY_APPS = [
                       'widget_tweaks',
                       'django_extensions',
                       "rest_framework",
                       "corsheaders",
                       'meta',
                       'sslserver'
                   ] + [
                       "formtools",  # wizard django officiel
                       "compressor"
                   ]

LOCAL_APPS = [
    "apps.accounts.apps.AccountsConfig",
    "apps.catalog.apps.CatalogConfig",
    "apps.content.apps.ContentConfig",
    "apps.billing.apps.BillingConfig",
    "apps.checkout.apps.CheckoutConfig",
    "apps.learning.apps.LearningConfig",
    "apps.leads.apps.LeadsConfig",
    "apps.marketing.apps.MarketingConfig",
    "apps.atelier.apps.AtelierConfig",
    "apps.pages.apps.PagesConfig",
    "apps.flowforms.apps.FlowFormsConfig",
    "apps.chatbot.apps.ChatbotConfig",
    "apps.adsbridge.apps.AdsBridgeConfig",
    "apps.messaging.apps.MessagingConfig",

]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS
# --------------------------------------------------------------------------------------
# Feature flags
# --------------------------------------------------------------------------------------
CHATBOT_ENABLED = _env_flag("CHATBOT_ENABLED", default=False)

# --------------------------------------------------------------------------------------
# Middleware
# WhiteNoise doit être juste après SecurityMiddleware
# --------------------------------------------------------------------------------------
MIDDLEWARE = [
                 "corsheaders.middleware.CorsMiddleware",
                 'django.middleware.security.SecurityMiddleware',
                 'apps.marketing.middleware.ConsentDebugHeadersMiddleware',
                 'whitenoise.middleware.WhiteNoiseMiddleware',  # <= ici
                 "apps.atelier.middleware.site_version.PathPrefixSiteVersionMiddleware",
             ] + [
                 "apps.atelier.middleware.request_id.RequestIdMiddleware",
                 "apps.atelier.middleware.segments.SegmentResolverMiddleware",
                 "apps.atelier.ab.middleware.ABBucketingCookieMiddleware",
                 "apps.atelier.middleware.vary.VaryHeadersMiddleware",

             ] + [
                 'django.contrib.sessions.middleware.SessionMiddleware',
                 'django.middleware.locale.LocaleMiddleware',  # ← ICI
                 'django.middleware.common.CommonMiddleware',
                 'django.middleware.csrf.CsrfViewMiddleware',
                 'django.contrib.auth.middleware.AuthenticationMiddleware',
                 'django.contrib.messages.middleware.MessageMiddleware',
                 'django.middleware.clickjacking.XFrameOptionsMiddleware',
                 "apps.marketing.middleware.SeoGuardMiddleware",
                 "apps.core.middleware.robots.RobotsTagMiddleware",
             ]

ROOT_URLCONF = 'alfenna.urls'

# --------------------------------------------------------------------------------------
# Templates
# --------------------------------------------------------------------------------------
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            BASE_DIR / 'templates',
            BASE_DIR / 'apps' / 'accounts' / 'templates',
            BASE_DIR / 'apps' / 'catalog' / 'templates',
            BASE_DIR / 'apps' / 'content' / 'templates',
            BASE_DIR / 'apps' / 'flowforms' / 'templates',
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.i18n',
                "apps.marketing.context_processors.seo",
            ],
        },
    },
]

WSGI_APPLICATION = 'alfenna.wsgi.application'
ASGI_APPLICATION = 'alfenna.asgi.application'

# --------------------------------------------------------------------------------------
# Database (100% Django, configurable via env)
# --------------------------------------------------------------------------------------
DB_ENGINE = os.getenv('DB_ENGINE', 'sqlite3')
if DB_ENGINE == 'sqlite3':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': DB_ENGINE,
            'NAME': os.getenv('DB_NAME', 'alfenna_db'),
            'USER': os.getenv('DB_USER', 'user_alfenna'),
            'PASSWORD': os.getenv('DB_PASSWORD', ''),
            'HOST': os.getenv('DB_HOST', '127.0.0.1'),
            'PORT': os.getenv('DB_PORT', '5432'),
        }
    }

# --------------------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# --------------------------------------------------------------------------------------
# I18N / TZ
# --------------------------------------------------------------------------------------
LANGUAGE_CODE = 'fr'
TIME_ZONE = 'Africa/Casablanca'
USE_I18N = True
USE_L10N = True
USE_TZ = True

LANGUAGES = [
    ('en', 'English'),
    ('fr', 'French'),
    ('ar', 'Arabic'),
]


LOCALE_PATHS = [BASE_DIR / 'locale']

# --------------------------------------------------------------------------------------
# Static & Media (Django 5)
# --------------------------------------------------------------------------------------
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
    "compressor.finders.CompressorFinder",
]

COMPRESS_ENABLED = True
COMPRESS_OFFLINE = False
COMPRESS_OUTPUT_DIR = "CACHE"
COMPRESS_CSS_FILTERS = [
    "compressor.filters.css_default.CssAbsoluteFilter",
    "compressor.filters.cssmin.CSSMinFilter",
]
COMPRESS_JS_FILTERS = [
    "compressor.filters.jsmin.JSMinFilter",
]

ATELIER_DISABLE_REGISTERED_ASSETS = False
ATELIER_STRIP_REGISTRY_ALIASES = ["vendors/core"]

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# --------------------------------------------------------------------------------------
# Sécurité (par défaut sûrs; dev.py relâche)
# --------------------------------------------------------------------------------------
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = "Lax"

SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

X_FRAME_OPTIONS = "DENY"

# Reverse proxy (si derrière un LB terminant TLS)
if os.getenv('USE_X_FORWARDED_PROTO', '1') in ('1', 'true', 'True'):
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# --------------------------------------------------------------------------------------
# Email (depuis env)
# --------------------------------------------------------------------------------------
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL')
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.titan.email')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '465'))
EMAIL_USE_SSL = os.getenv('EMAIL_USE_SSL', '1') in ('1', 'true', 'True')
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', '0') in ('1', 'true', 'True')
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD')
MESSAGING_SECURE_BASE_URL = os.getenv('MESSAGING_SECURE_BASE_URL')
PASSWORD_RESET_TIMEOUT = int(os.getenv('PASSWORD_RESET_TIMEOUT_SECONDS', '3600'))

# E-mail preflight / guard rails ------------------------------------------------------
EMAIL_BACKEND_ENFORCE_SMTP = env_flag("EMAIL_BACKEND_ENFORCE_SMTP", default=False)
EMAIL_PREFLIGHT_REQUIRED = env_flag("EMAIL_PREFLIGHT_REQUIRED", default=False)
EMAIL_PREFLIGHT_MODE = os.getenv("EMAIL_PREFLIGHT_MODE", "connect").strip().lower() or "connect"
if EMAIL_PREFLIGHT_MODE not in {"connect", "send"}:
    EMAIL_PREFLIGHT_MODE = "connect"
EMAIL_PREFLIGHT_TO = os.getenv("EMAIL_PREFLIGHT_TO", "").strip()
EMAIL_PREFLIGHT_TIMEOUT = int(os.getenv("EMAIL_PREFLIGHT_TIMEOUT", "8"))

# Email rate limiting -------------------------------------------------------------
EMAIL_RATE_LIMIT = {
    "password_reset": {
        "window_seconds": max(1, _int_env("EMAIL_RATE_PASSWORD_RESET_WINDOW_SECONDS", 300)),
        "max_per_window": max(1, _int_env("EMAIL_RATE_PASSWORD_RESET_MAX", 5)),
        "include_failed": _env_flag("EMAIL_RATE_PASSWORD_RESET_INCLUDE_FAILED", default=True),
    },
    "email_verification": {
        "window_seconds": max(1, _int_env("EMAIL_RATE_EMAIL_VERIFICATION_WINDOW_SECONDS", 300)),
        "max_per_window": max(1, _int_env("EMAIL_RATE_EMAIL_VERIFICATION_MAX", 5)),
        "include_failed": _env_flag("EMAIL_RATE_EMAIL_VERIFICATION_INCLUDE_FAILED", default=True),
    },
}

# --------------------------------------------------------------------------------------
# Logging (propre, exploitable)
# --------------------------------------------------------------------------------------
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {'format': '[{levelname}] {name}: {message}', 'style': '{'},
        'verbose': {'format': '{asctime} [{levelname}] {name} {module}:{lineno} — {message}', 'style': '{'},
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'formatter': 'verbose'},
    },
    'root': {'handlers': ['console'], 'level': LOG_LEVEL},
    'loggers': {
        'django.request': {'handlers': ['console'], 'level': 'WARNING', 'propagate': True},
        'OnlineLearning': {'handlers': ['console'], 'level': LOG_LEVEL, 'propagate': False},
    },
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Billing / Stripe --------------------------------------------------------------------
from .components.billing import *  # noqa: F401,F403

# --------------------------------------------------------------------------------------
# Video Learning
# --------------------------------------------------------------------------------------

VIDEO_STREAM_CHUNK_BYTES = 512 * 1024

# Feature flags -----------------------------------------------------------------------
ANALYTICS_ENABLED = True

# --------------------------------------------------------------------------------------
# Redis / Celery
# --------------------------------------------------------------------------------------


# --- Cache Redis (obligatoire pour throttle & idem) ---
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/3")

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://127.0.0.1:6379/3",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            # "PARSER_CLASS": "redis.connection.HiredisParser",  # ← SUPPRIMER
            "COMPRESSOR": "django_redis.compressors.zlib.ZlibCompressor",
            "IGNORE_EXCEPTIONS": True,  # dev: pas de 500 si Redis down
        },
        "KEY_PREFIX": "alfenna",
        "TIMEOUT": 300,
    }
}

# --- Celery ---
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/3")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/3")
CELERY_TASK_ALWAYS_EAGER = False  # True en dev si tu veux exécuter inline
CELERY_TASK_TIME_LIMIT = 60
CELERY_TASK_SOFT_TIME_LIMIT = 45
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_QUEUES = {
    "default": {},
    "leads": {},
    "analytics": {},
    "email": {},
}
CELERY_WORKER_MAX_TASKS_PER_CHILD = 1000
CELERY_WORKER_CONCURRENCY = int(os.getenv("CELERY_WORKER_CONCURRENCY", "4"))
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TASK_ROUTES = {
    "apps.messaging.tasks.send_outbox_email": {"queue": "email"},
    "apps.messaging.tasks.drain_outbox_batch": {"queue": "email"},
    "apps.messaging.tasks.enqueue_render_from_template": {"queue": "email"},
    "apps.messaging.tasks.schedule_campaigns": {"queue": "email"},
    "apps.messaging.tasks.process_campaign": {"queue": "email"},
}
CELERY_BEAT_SCHEDULE = {
    "chatbot-purge-history": {
        "task": "apps.chatbot.tasks.purge_chat_messages_older_than",
        "schedule": crontab(minute=0, hour=3),
    },
    "messaging.drain_outbox": {
        "task": "apps.messaging.tasks.drain_outbox_batch",
        "schedule": crontab(minute="*"),
        "options": {"queue": "email"},
    },
    "messaging.campaigns": {
        "task": "apps.messaging.tasks.schedule_campaigns",
        "schedule": crontab(minute="*/5"),
        "options": {"queue": "email"},
    },
}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],  # public endpoint
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_THROTTLE_CLASSES": [
        "apps.leads.throttling.LeadsIPThrottle",
        "apps.leads.throttling.LeadsEmailThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "leads_ip": "30/min",  # par IP, tous formulaires
        "leads_email": "10/min",  # par email normalisé
        "messaging_ip": os.getenv("MESSAGING_THROTTLE_IP", "15/min"),
        "messaging_email": os.getenv("MESSAGING_THROTTLE_EMAIL", "5/hour"),
    },
}

# --- Sécurité signature & politique champs ---
LEADS_SIGNING_SECRET = os.getenv("LEADS_SIGNING_SECRET", "change-me-please")
LEADS_POLICY_YAML = os.getenv("LEADS_POLICY_YAML", os.path.join(BASE_DIR, "configs", "leads_fields.yaml"))
LEADS_REQUIRED_PRIORITY = ["db", "yaml", "settings"]  # ordre de fusion

# --- Logs structurés conseillés ---
LOGGING["loggers"].update({
    "leads.api": {"handlers": ["console"], "level": "INFO"},
    "leads.antispam": {"handlers": ["console"], "level": "INFO"},
    "leads.tasks": {"handlers": ["console"], "level": "INFO"},
    "leads.enrich": {"handlers": ["console"], "level": "INFO"},
    "leads.route": {"handlers": ["console"], "level": "INFO"},
    "leads.audit": {"handlers": ["console"], "level": "INFO"},
})

LOGGING["loggers"].update({
    "chatbot.api": {"handlers": ["console"], "level": "INFO"},
    "chatbot.stream": {"handlers": ["console"], "level": "INFO"},
    "chatbot.service": {"handlers": ["console"], "level": "INFO"},
    "chatbot.metrics": {"handlers": ["console"], "level": "INFO"},
    "chatbot.tasks": {"handlers": ["console"], "level": "INFO"},
})

LOGGING["loggers"].update({
    "marketing.seo": {"handlers": ["console"], "level": "INFO"},
    "messaging.tasks": {"handlers": ["console"], "level": "INFO"},
    "messaging.integrations": {"handlers": ["console"], "level": "INFO"},
    "messaging.campaigns": {"handlers": ["console"], "level": "INFO"},
    "messaging.views": {"handlers": ["console"], "level": "INFO"},
    "messaging.admin": {"handlers": ["console"], "level": "INFO"},
})

# --------------------------------------------------------------------------------------
# SEO
# --------------------------------------------------------------------------------------


SEO_ENV = os.getenv("SEO_ENV", "dev")  # dev|stage|prod
SEO_FORCE_NOINDEX_NONPROD = True
SEO_EXTRA_PRIVATE_PATH_PREFIXES = (
    "/admin/",
    "/staging/",
)
SEO_ALLOWED_QUERY_CANONICAL = ["page"]  # seules ces query passent dans canonical
SEO_STRICT_CANONICAL = False  # True => 301 vers canonical nettoyée
SEO_DEFAULT_LOCALE = "fr_FR"

ENABLE_STATIC_DEBUG_VIEW = False

# Valeurs par défaut (surchargées par DB via MarketingGlobal)
SEO_DEFAULTS = {
    "site_name": "Lumière Learning",
    "base_url": os.getenv("SEO_BASE_URL", "http://localhost:8000"),
    "default_image": "/static/img/og-default.png",
    "twitter_site": "@alfenna",
    "twitter_creator": "@alfenna",
    "facebook_app_id": "",
}

# Tracking IDs (peuvent rester vides ; DB pourra les fournir)
TRACKING_IDS = {
    "GTM_ID": os.getenv("GTM_ID", ""),  # GTM-XXXX
    "GA4_ID": os.getenv("GA4_ID", ""),  # G-XXXX
    "META_PIXEL_ID": os.getenv("META_PIXEL_ID", ""),
    "TIKTOK_PIXEL_ID": os.getenv("TIKTOK_PIXEL_ID", ""),
}

CONSENT_COOKIE_NAME = "cookie_consent_marketing"
CHATBOT_RETENTION_DAYS = int(os.getenv("CHATBOT_RETENTION_DAYS", "30"))
CHATBOT_THROTTLE_RATES = {
    "chat_ip": os.getenv("CHATBOT_THROTTLE_IP", "30/min"),
    "chat_session": os.getenv("CHATBOT_THROTTLE_SESSION", "8/min"),
}
CHATBOT_DEFAULT_PROVIDER = os.getenv("CHATBOT_DEFAULT_PROVIDER", "mock")
CHATBOT_MODEL_NAME = os.getenv("CHATBOT_MODEL_NAME", "mock-gpt")
CHATBOT_FALLBACK_MESSAGE = "Je rencontre un souci temporaire, merci de réessayer ultérieurement."
CHATBOT_PROVIDER_FAILURE_THRESHOLD = int(os.getenv("CHATBOT_PROVIDER_FAILURE_THRESHOLD", "3"))
CHATBOT_PROVIDER_CIRCUIT_TTL = int(os.getenv("CHATBOT_PROVIDER_CIRCUIT_TTL", "300"))

# --- django-meta (config minimale ; le reste piloté par mixins/CP) ---
META_USE_SITES = False
META_SITE_DOMAIN = "localhost"
META_SITE_PROTOCOL = "https" if not DEBUG else "http"
META_DEFAULT_KEYWORDS = ["cours", "e-learning", "formation", "vidéo"]
META_INCLUDE_KEYWORDS = ["python", "apprentissage"]
META_OG_NAMESPACES = ["og", "article", "product", "website"]
META_TWITTER_TYPES = ["summary", "summary_large_image"]
META_USE_OG_PROPERTIES = True
META_USE_TWITTER_PROPERTIES = True

# --------------------------------------------------------------------------------------
# Variants d'images par collectstatic
# --------------------------------------------------------------------------------------

# --- Variants d’images par collectstatic ---
ATELIER_IMAGE_VARIANTS = {
    # ordre de préférence dans <picture>
    "enabled": ["avif", "webp", "png"],
    # largeur max avant redimensionnement (0 = pas de resize)
    "max_width": 1920,
    # qualités / paramètres par format
    "quality": {
        "webp": 85,  # 0..100
        "png": 9  # compress_level (0..9)
    },
    # extensions source à traiter (hors svg/gif/ico)
    "process_ext": [".jpg", ".jpeg", ".png", ".webp"],
}

# --- Brancher le storage custom (serveur & collectstatic) ---
STORAGES["staticfiles"] = {
    "BACKEND": "apps.atelier.staticbuild.storage.VariantManifestStaticFilesStorage"
}

# --------------------------------------------------------------------------------------
# Signing Token Leads
# --------------------------------------------------------------------------------------
LEADS_SIGNING_MAX_AGE = 7200
LEADS_SIGNING_DROP_EMPTY = True  # ← rend tolérant (""/None/{}) ignorés
# --------------------------------------------------------------------------------------
# Redis / Celery
# --------------------------------------------------------------------------------------
FLOWFORMS_POLICY_YAML = Path(BASE_DIR) / "configs" / "flowforms.yaml"

# === FlowForms defaults (self-config component) ===
FLOWFORMS_DEFAULT_FLOW_KEY = "checkout_intent_flow"
FLOWFORMS_ENDPOINT_COLLECT_URLNAME = "leads:collect"
FLOWFORMS_REQUIRE_SIGNED = True
FLOWFORMS_SIGN_URLNAME = "leads:sign"
FLOWFORMS_COMPONENT_ENABLED = True

# 🔵 Étape 2 — flag d’activation du wiring Compose/Children pour forms/shell
FLOWFORMS_USE_CHILD_COMPOSE = False

LOGGING["loggers"].update({
    "forms.shell.contracts": {"handlers": ["console"], "level": "INFO"},
})

# --------------------------------------------------------------------------------------
# Login
# --------------------------------------------------------------------------------------
LOGIN_URL = "pages:login"  # au lieu d'un chemin en dur
LOGIN_REDIRECT_URL = "pages:home"  # ce que tu voulais
LOGOUT_REDIRECT_URL = "pages:home"

# --------------------------------------------------------------------------------------
# Ads bridge
# --------------------------------------------------------------------------------------

DEFAULT_GADS_CONFIGURATION_PATH = BASE_DIR / "credentials" / "google-ads.yaml"

GADS_ENABLED = env_flag("GADS_ENABLED", default=True)
ADS_S2S_MODE = os.getenv("ADS_S2S_MODE", "on").strip().lower()
GADS_VALIDATE_ONLY = env_flag("GADS_VALIDATE_ONLY", default=True)  # False en prod réelle
GADS_PARTIAL_FAILURE = env_flag("GADS_PARTIAL_FAILURE", default=True)
GADS_PREVERIFY_ACTIONS = env_flag("GADS_PREVERIFY_ACTIONS", default=True)
GADS_CONFIGURATION_PATH = Path(os.getenv("GADS_CONFIGURATION_PATH", str(DEFAULT_GADS_CONFIGURATION_PATH))).expanduser()
GADS_CUSTOMER_ID = (os.getenv("GADS_CUSTOMER_ID") or "").strip()
GADS_LOGIN_CUSTOMER_ID = (os.getenv("GADS_LOGIN_CUSTOMER_ID") or "").strip()

_lead_submit_id = (os.getenv("GADS_ACTION_LEAD_SUBMIT_ID") or "").strip()
_lead_submit_rn = (os.getenv("GADS_ACTION_LEAD_SUBMIT_RN") or "").strip()

GADS_CONVERSION_ACTIONS: dict[str, dict[str, str]] = {}

if _lead_submit_id or _lead_submit_rn:
    lead_submit_payload: dict[str, str] = {}
    if _lead_submit_id:
        lead_submit_payload["id"] = _lead_submit_id
    if _lead_submit_rn:
        lead_submit_payload["resource_name"] = _lead_submit_rn
    GADS_CONVERSION_ACTIONS["lead_submit"] = lead_submit_payload

# MIME types pour images modernes
import mimetypes

mimetypes.add_type("image/avif", ".avif", strict=False)
mimetypes.add_type("image/webp", ".webp", strict=False)
