# wsgi.py
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'alfenna.settings.dev')
application = get_wsgi_application()

from django.conf import settings  # noqa: E402  - imported after setup

if getattr(settings, "EMAIL_PREFLIGHT_REQUIRED", False):
    from apps.messaging.health import ensure_email_ready  # noqa: E402

    ensure_email_ready(raise_on_fail=True)
