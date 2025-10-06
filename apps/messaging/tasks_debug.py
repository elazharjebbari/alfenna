from __future__ import annotations

import os

from celery import shared_task


@shared_task(name="debug.dump_env_email_settings", queue="email")
def dump_env_email_settings():
    keys = [
        "EMAIL_HOST",
        "EMAIL_PORT",
        "EMAIL_USE_SSL",
        "EMAIL_USE_TLS",
        "EMAIL_HOST_USER",
        "DEFAULT_FROM_EMAIL",
        "MESSAGING_SECURE_BASE_URL",
    ]
    values = []
    for key in keys:
        value = os.getenv(key) or ""
        if "PASSWORD" in key or "HOST_USER" in key:
            value = "set" if value else "MISSING"
        values.append(f"{key}={value}")
    return " | ".join(values)
