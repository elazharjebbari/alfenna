# apps/messaging/scripts/diag_email_pipeline.py
from __future__ import annotations
import os, socket, smtplib, sys, json, time
from typing import Any, Dict
from django.conf import settings
from django.urls import reverse
from django.core.mail import get_connection
from django.db import connection
from django.test import Client
from django.utils import timezone

from apps.messaging.models import OutboxEmail, EmailTemplate
from apps.messaging.template_loader import FileSystemTemplateLoader
from apps.messaging.tasks import drain_outbox_batch

ICON = {
    "ok": "✅",
    "warn": "⚠️",
    "err": "❌",
    "info": "ℹ️",
    "bullet": "•",
}

def line(kind, msg):
    print(f"{ICON.get(kind,'•')}  {msg}")

def kv(k, v):
    print(f"   {k:<28} {v}")

def _bool(v: Any) -> str:
    return "1" if str(v).strip().lower() in {"1","true","yes","on"} else "0"

def run():
    print("\n=== DIAG EMAIL PIPELINE ===\n")

    # 0) Contexte
    line("info", "Contexte")
    kv("DJANGO_SETTINGS_MODULE", os.getenv("DJANGO_SETTINGS_MODULE"))
    kv("ENV DEV_EMAIL_CONSOLE", os.getenv("DEV_EMAIL_CONSOLE", ""))
    kv("settings.EMAIL_BACKEND", getattr(settings, "EMAIL_BACKEND", ""))
    kv("EMAIL_HOST", getattr(settings, "EMAIL_HOST", ""))
    kv("EMAIL_PORT", getattr(settings, "EMAIL_PORT", ""))
    kv("EMAIL_USE_SSL", getattr(settings, "EMAIL_USE_SSL", ""))
    kv("EMAIL_USE_TLS", getattr(settings, "EMAIL_USE_TLS", ""))
    kv("EMAIL_HOST_USER", "set" if bool(getattr(settings, "EMAIL_HOST_USER", "")) else "MISSING")
    kv("DEFAULT_FROM_EMAIL", getattr(settings, "DEFAULT_FROM_EMAIL", ""))
    kv("MESSAGING_SECURE_BASE_URL", getattr(settings, "MESSAGING_SECURE_BASE_URL", ""))
    kv("CELERY_TASK_ALWAYS_EAGER", getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False))
    print()

    # 1) Avertissements usuels
    if "console" in str(getattr(settings, "EMAIL_BACKEND", "")).lower():
        line("warn", "EMAIL_BACKEND=console: les mails s’impriment dans le terminal, pas d’envoi SMTP.")
    if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
        line("warn", "CELERY_TASK_ALWAYS_EAGER=TRUE: rien n’apparaîtra dans Flower/worker.")

    # 2) SMTP “préflight” (optionnel si backend console)
    backend = str(getattr(settings, "EMAIL_BACKEND", "")).lower()
    if "smtp" in backend:
        try:
            conn = get_connection()  # django.core.mail backend
            conn.open()
            line("ok", f"Connexion SMTP OK → {getattr(settings,'EMAIL_HOST','')}:{getattr(settings,'EMAIL_PORT','')}")
        except Exception as e:
            line("err", f"Connexion SMTP KO: {e!r}")
            return
    else:
        line("info", "Skip test SMTP (backend non SMTP).")

    # 3) Vérifier les templates (catalogue en BD, sinon sync depuis le disque)
    loader = FileSystemTemplateLoader()
    created = loader.sync()  # idempotent
    total = EmailTemplate.objects.count()
    line("ok" if total else "err", f"Templates en BD: {total} (nouveaux: {len(created)})")  # loader.sync existe
    # (Le loader lit templates/email/*/<locale>/*.subject.txt + .html + .txt)  # Doc du loader

    # 4) Enqueue & drain minimal (sans HTTP)
    before = OutboxEmail.objects.count()
    # Envoi d’un email “diagnostic” avec un template jetable (si tu veux)
    tpl, _ = EmailTemplate.objects.get_or_create(
        slug="scripts/diagnostic", locale="fr",
        defaults={"version":1,"subject":"Diag","html_template":"<p>Diag</p>","text_template":"Diag"},
    )
    from apps.messaging.services import EmailService
    outbox = EmailService.compose_and_enqueue(
        namespace="scripts",
        purpose="diagnostic",
        template_slug=tpl.slug,
        to=["diagnostic@example.com"],
        dedup_key=f"diag-{timezone.now().timestamp()}",
    )
    after = OutboxEmail.objects.count()
    if after == before + 1:
        line("ok", f"Outbox enqueue OK (id={outbox.id})")
    else:
        line("err", "Outbox enqueue KO (aucune ligne créée)")
        return

    # 5) Drain: forcer un passage de delivery
    try:
        drained = drain_outbox_batch(limit=10)
        line("info", f"drain_outbox_batch → {drained}")
    except Exception as e:
        line("err", f"Drain KO: {e!r}")
        return

    # 6) Statut final
    outbox.refresh_from_db()
    kv("Outbox.status", outbox.status)
    kv("Attempts", outbox.attempts.count())
    if outbox.status == OutboxEmail.Status.SENT:
        line("ok", "Delivery SENT ✅")
    elif outbox.status == OutboxEmail.Status.FAILED:
        kv("last_error_code", outbox.last_error_code)
        kv("last_error_message", outbox.last_error_message)
        line("err", "Delivery FAILED ❌ (vois l’erreur ci-dessus)")
    else:
        line("warn", "Delivery non SENT (queue/worker non démarrés ou backend console).")

    print("\n=== FIN DIAG ===\n")
