from __future__ import annotations

from django.conf import settings

from apps.messaging.services import EmailService, schedule_outbox_drain


DEFAULT_EMAIL = "elazhar.jebbari@gmail.com"
TEMPLATE_SLUG = "accounts/verify"


def run(*args):
    """Send a test email using the messaging pipeline.

    Usage:
        python manage.py runscript scripts.send_test_email
        python manage.py runscript scripts.send_test_email --script-args you@example.com
    """

    target_email = (args[0].strip() if args else DEFAULT_EMAIL)
    if not target_email:
        raise ValueError("A valid target email address is required.")

    site_name = getattr(settings, "SITE_NAME", "Lumière Academy")
    support_email = getattr(settings, "SUPPORT_EMAIL", settings.DEFAULT_FROM_EMAIL)

    outbox = EmailService.compose_and_enqueue(
        namespace="scripts",
        purpose="manual_test",
        template_slug=TEMPLATE_SLUG,
        to=[target_email],
        context={
            "user_first_name": "Test",
            "verification_url": f"{getattr(settings, 'SITE_BASE_URL', 'https://lumiereacademy.com')}/",
            "verification_ttl_hours": 1,
            "site_name": site_name,
            "support_email": support_email,
        },
        metadata={"initiator": "scripts.send_test_email"},
    )

    # Trigger the outbox drain immediately (works with eager Celery too).
    schedule_outbox_drain()

    print(
        f"Test email enqueued for {target_email}. Outbox id={outbox.id}. "
        "Ensure the Celery worker is running so the message is delivered."
    )
