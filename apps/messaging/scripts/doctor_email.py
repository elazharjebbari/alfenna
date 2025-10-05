# apps/messaging/scripts/doctor_email.py
from __future__ import annotations
import os, sys, time
from typing import Any
from django.conf import settings
from django.core.mail import get_connection, send_mail
from django.utils import timezone

from apps.messaging.models import OutboxEmail, EmailTemplate
from apps.messaging.template_loader import FileSystemTemplateLoader
from apps.messaging.tasks import drain_outbox_batch

ICON = {"ok":"✅","warn":"⚠️","err":"❌","info":"ℹ️","bullet":"•"}

def p(k,v): print(f"   {k:<28} {v}")
def L(kind,msg): print(f"{ICON.get(kind,'•')}  {msg}")

def run(*args):
    print("\n=== DOCTOR EMAIL — full pipeline check ===\n")

    # 0) ENV snapshot
    L("info","Environment & settings")
    p("DJANGO_SETTINGS_MODULE", os.getenv("DJANGO_SETTINGS_MODULE"))
    p("DEFAULT_FROM_EMAIL", getattr(settings,"DEFAULT_FROM_EMAIL","-"))
    p("EMAIL_BACKEND", getattr(settings,"EMAIL_BACKEND","-"))
    p("EMAIL_HOST", getattr(settings,"EMAIL_HOST","-"))
    p("EMAIL_PORT", getattr(settings,"EMAIL_PORT","-"))
    p("EMAIL_USE_SSL", getattr(settings,"EMAIL_USE_SSL","-"))
    p("EMAIL_USE_TLS", getattr(settings,"EMAIL_USE_TLS","-"))
    p("EMAIL_HOST_USER", "set" if getattr(settings,"EMAIL_HOST_USER","") else "MISSING")
    p("EMAIL_HOST_PASSWORD", "set" if getattr(settings,"EMAIL_HOST_PASSWORD","") else "MISSING")
    p("MESSAGING_SECURE_BASE_URL", getattr(settings,"MESSAGING_SECURE_BASE_URL","-"))
    p("CELERY_TASK_ALWAYS_EAGER", getattr(settings,"CELERY_TASK_ALWAYS_EAGER", False))
    print()

    # Hints
    if "console" in str(getattr(settings,"EMAIL_BACKEND","")).lower():
        L("warn","EMAIL_BACKEND=console → pas d’envoi réel (normal en dev).")
    if getattr(settings,"CELERY_TASK_ALWAYS_EAGER", False):
        L("warn","CELERY_TASK_ALWAYS_EAGER=True → rien dans Flower, exécution inline.")

    # 1) Préflight SMTP si backend SMTP
    backend = str(getattr(settings,"EMAIL_BACKEND","")).lower()
    if "smtp" in backend:
        try:
            conn = get_connection()
            if hasattr(conn,"timeout") and not getattr(conn,"timeout",None):
                conn.timeout = int(os.getenv("EMAIL_PREFLIGHT_TIMEOUT","8"))
            conn.open()
            L("ok", f"SMTP connect OK → {settings.EMAIL_HOST}:{settings.EMAIL_PORT}")
            conn.close()
        except Exception as e:
            L("err", f"SMTP connect FAILED: {e!r}")
            print("\nAstuce:")
            print("  • Si Gmail: activer 2FA + App Password (et host_user doit être le compte Google réel).")
            print("  • Si Titan/OVH: utilisez leur SMTP (host/port/SSL) au lieu de smtp.gmail.com.")
            print("  • Vérifier EMAIL_USE_TLS/SSL/PORT (587/TLS ou 465/SSL, pas les deux).")
            return
    else:
        L("info","Skip SMTP preflight (backend non SMTP).")

    # 2) Templates en base (loader FS idempotent)
    try:
        loader = FileSystemTemplateLoader()
        created = loader.sync()
        total = EmailTemplate.objects.count()
        L("ok" if total else "err", f"Templates en base: {total} (nouveaux sync: {len(created)})")
        if not total:
            return
    except Exception as e:
        L("err", f"Template sync FAILED: {e!r}")
        return

    # 3) Enqueue un mail de diagnostic
    from apps.messaging.services import EmailService
    slug = "scripts/diagnostic"
    EmailTemplate.objects.get_or_create(
        slug=slug, locale="fr",
        defaults={"version":1,"subject":"Diag","html_template":"<p>Diag</p>","text_template":"Diag"},
    )
    before = OutboxEmail.objects.count()
    ob = EmailService.compose_and_enqueue(
        namespace="doctor",
        purpose="diagnostic",
        template_slug=slug,
        to=[getattr(settings,"EMAIL_HOST_USER","noreply@example.com") or "noreply@example.com"],
        dedup_key=f"doctor-{timezone.now().timestamp()}",
        metadata={"source":"doctor_email"},
    )
    after = OutboxEmail.objects.count()
    if after == before + 1:
        L("ok", f"Outbox enqueue OK (id={ob.id})")
    else:
        L("err", "Outbox enqueue KO")
        return

    # 4) Drain batch maintenant
    try:
        d = drain_outbox_batch(limit=20)
        L("info", f"drain_outbox_batch → {d}")
    except Exception as e:
        L("err", f"Drain FAILED: {e!r}")
        return

    # 5) Statut final + derniers échecs
    ob.refresh_from_db()
    p("Outbox.status", ob.status)
    p("Attempts", ob.attempts.count())
    if ob.status == OutboxEmail.Status.SENT:
        L("ok","Delivery SENT ✅")
    else:
        last = ob.attempts.order_by("-id").first()
        if last:
            p("smtp_response", getattr(last,"smtp_response","-"))
        p("last_error", getattr(ob,"last_error_message","-"))
        if ob.status == OutboxEmail.Status.FAILED:
            L("err","Delivery FAILED ❌ (voir l’erreur au-dessus)")
        else:
            L("warn","Delivery non SENT (worker/queue/SMTP?).")

    print("\n=== END DOCTOR ===\n")
