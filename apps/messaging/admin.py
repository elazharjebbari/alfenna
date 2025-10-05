"""Admin registrations arrive with the observability step."""
from __future__ import annotations

import csv
from typing import Iterable

from django.contrib import admin, messages
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse
from django.utils import timezone
from django.utils.html import escape

from .campaigns import CampaignService
from .models import Campaign, CampaignRecipient, EmailAttempt, EmailTemplate, OutboxEmail
from .services import EmailService, TemplateService, schedule_outbox_drain


def _schedule_outbox_drain() -> None:
    transaction.on_commit(schedule_outbox_drain)


@admin.register(EmailAttempt)
class EmailAttemptAdmin(admin.ModelAdmin):
    list_display = ("outbox", "status", "duration_ms", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("outbox__dedup_key", "error_message")
    readonly_fields = ("outbox", "status", "provider_message_id", "error_code", "error_message", "response_payload", "metadata", "duration_ms", "created_at", "updated_at")


class EmailAttemptInline(admin.TabularInline):
    model = EmailAttempt
    extra = 0
    can_delete = False
    readonly_fields = ("status", "created_at", "duration_ms", "error_message")
    ordering = ("-created_at",)


@admin.action(description="Ré-enfiler les e-mails sélectionnés")
def requeue_emails(modeladmin, request, queryset):
    updated = queryset.update(
        status=OutboxEmail.Status.QUEUED,
        scheduled_at=timezone.now(),
        locked_at=None,
        locked_by="",
        last_error_message="",
    )
    modeladmin.message_user(request, f"{updated} e-mails ré-enfilés.")
    if updated:
        _schedule_outbox_drain()


@admin.action(description="Supprimer des envois (supprimer)")
def suppress_emails(modeladmin, request, queryset):
    updated = queryset.update(
        status=OutboxEmail.Status.SUPPRESSED,
        locked_at=None,
        locked_by="",
    )
    modeladmin.message_user(request, f"{updated} e-mails supprimés.")


@admin.action(description="Réenvoyer une nouvelle copie")
def resend_emails(modeladmin, request, queryset):
    count = 0
    for outbox in queryset.order_by("pk"):
        dedup_suffix = timezone.now().strftime("%Y%m%d%H%M%S%f")
        explicit_key = f"{outbox.dedup_key}:resend:{dedup_suffix}"[:128]
        EmailService.compose_and_enqueue(
            namespace=outbox.namespace,
            purpose=outbox.purpose,
            template_slug=outbox.template_slug,
            to=outbox.to,
            locale=outbox.locale,
            context=outbox.context,
            dedup_key=explicit_key,
            scheduled_at=timezone.now(),
            priority=outbox.priority,
            cc=outbox.cc,
            bcc=outbox.bcc,
            reply_to=outbox.reply_to,
            headers=outbox.headers,
            attachments=outbox.attachments,
            metadata=outbox.metadata,
            subject_override=outbox.subject_override or None,
        )
        count += 1
    modeladmin.message_user(request, f"{count} nouvelles tentatives programmées.")


@admin.action(description="Exporter en CSV")
def export_emails_csv(modeladmin, request, queryset):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = "attachment; filename=outbox_emails.csv"
    writer = csv.writer(response)
    writer.writerow([
        "id",
        "namespace",
        "purpose",
        "status",
        "primary_recipient",
        "template_slug",
        "scheduled_at",
        "attempt_count",
        "last_error_at",
        "last_error_message",
    ])
    for email in queryset.order_by("id"):
        writer.writerow([
            email.pk,
            email.namespace,
            email.purpose,
            email.status,
            email.primary_recipient,
            email.template_slug,
            timezone.localtime(email.scheduled_at) if email.scheduled_at else "",
            email.attempt_count,
            timezone.localtime(email.last_error_at) if email.last_error_at else "",
            email.last_error_message,
        ])
    return response


@admin.register(OutboxEmail)
class OutboxEmailAdmin(admin.ModelAdmin):
    list_display = (
        "namespace",
        "purpose",
        "status",
        "primary_recipient",
        "template_slug",
        "scheduled_at",
        "attempt_count",
        "last_error_at",
    )
    list_filter = ("namespace", "purpose", "status", "priority", "scheduled_at")
    search_fields = ("dedup_key", "to", "subject_override", "rendered_subject", "provider_message_id")
    date_hierarchy = "scheduled_at"
    list_select_related = False
    readonly_fields = (
        "namespace",
        "purpose",
        "dedup_key",
        "to",
        "cc",
        "bcc",
        "reply_to",
        "locale",
        "template_slug",
        "template_version",
        "rendered_subject",
        "rendered_html",
        "rendered_text",
        "context",
        "headers",
        "attachments",
        "status",
        "priority",
        "attempt_count",
        "scheduled_at",
        "locked_at",
        "locked_by",
        "sent_at",
        "last_error_at",
        "last_error_message",
        "provider_message_id",
        "metadata",
        "created_at",
        "updated_at",
    )
    inlines = [EmailAttemptInline]
    actions = [requeue_emails, suppress_emails, resend_emails, export_emails_csv]


@admin.action(description="Activer les templates sélectionnés")
def activate_templates(modeladmin, request, queryset):
    count = queryset.update(is_active=True)
    modeladmin.message_user(request, f"{count} templates activés")


@admin.action(description="Désactiver les templates sélectionnés")
def deactivate_templates(modeladmin, request, queryset):
    count = queryset.update(is_active=False)
    modeladmin.message_user(request, f"{count} templates désactivés")


@admin.action(description="Prévisualiser le template")
def preview_template(modeladmin, request, queryset):
    templates = list(queryset[:2])
    if not templates:
        modeladmin.message_user(request, "Aucun template sélectionné.", level=messages.WARNING)
        return None
    if len(templates) > 1:
        modeladmin.message_user(request, "Sélectionne un seul template pour la prévisualisation.", level=messages.WARNING)
        return None
    template = templates[0]
    context = {}
    metadata = template.metadata if isinstance(template.metadata, dict) else {}
    sample_context = metadata.get("sample_context") if isinstance(metadata, dict) else None
    if isinstance(sample_context, dict):
        context = sample_context
    try:
        composition = TemplateService.render(template, context)
    except Exception as exc:
        modeladmin.message_user(request, f"Erreur de rendu: {exc}", level=messages.ERROR)
        return None

    html_preview = composition.html_body
    text_preview = escape(composition.text_body)
    subject_preview = escape(composition.subject)
    response = HttpResponse(content_type="text/html; charset=utf-8")
    response.write(
        """
        <!DOCTYPE html>
        <html lang=\"fr\">
          <head>
            <meta charset=\"utf-8\">
            <title>Prévisualisation template</title>
            <style>
              body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 24px; }
              .section { margin-bottom: 32px; }
              .section h2 { margin-bottom: 8px; }
              iframe { border: 1px solid #ddd; width: 100%; min-height: 420px; }
              pre { background: #f6f6f8; padding: 12px; border-radius: 6px; white-space: pre-wrap; }
            </style>
          </head>
          <body>
        """
    )
    response.write(f"<h1>{escape(template.slug)} · v{template.version} ({template.locale})</h1>")
    response.write("<section class='section'><h2>Sujet</h2><pre>")
    response.write(subject_preview)
    response.write("</pre></section>")
    response.write("<section class='section'><h2>Version texte</h2><pre>")
    response.write(text_preview)
    response.write("</pre></section>")
    response.write("<section class='section'><h2>Version HTML</h2><div style='border:1px solid #ddd;border-radius:6px;padding:16px;'>")
    response.write(html_preview)
    response.write("</div></section>")
    response.write("</body></html>")
    return response


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ("slug", "locale", "version", "is_active", "updated_at")
    list_filter = ("locale", "is_active")
    search_fields = ("slug", "subject")
    readonly_fields = ("slug", "locale", "version", "subject", "html_template", "text_template", "metadata", "created_at", "updated_at")
    actions = [activate_templates, deactivate_templates, preview_template]


@admin.action(description="Planifier maintenant")
def schedule_now(modeladmin, request, queryset):
    now = timezone.now()
    updated = queryset.update(scheduled_at=now, status=Campaign.Status.SCHEDULED)
    modeladmin.message_user(request, f"{updated} campagnes planifiées immédiatement")


@admin.action(description="Lancer les campagnes")
def start_campaigns(modeladmin, request, queryset):
    updated = queryset.filter(status__in=[Campaign.Status.DRAFT, Campaign.Status.SCHEDULED, Campaign.Status.PAUSED]).update(status=Campaign.Status.RUNNING)
    modeladmin.message_user(request, f"{updated} campagnes en cours")


@admin.action(description="Mettre en pause")
def pause_campaigns(modeladmin, request, queryset):
    updated = queryset.filter(status=Campaign.Status.RUNNING).update(status=Campaign.Status.PAUSED)
    modeladmin.message_user(request, f"{updated} campagnes mises en pause")


@admin.action(description="Marquer complétées")
def complete_campaigns(modeladmin, request, queryset):
    updated = queryset.exclude(status=Campaign.Status.COMPLETED).update(status=Campaign.Status.COMPLETED)
    modeladmin.message_user(request, f"{updated} campagnes complétées")


@admin.action(description="Enfiler les destinataires en attente")
def enqueue_pending(modeladmin, request, queryset):
    total = 0
    for campaign in queryset:
        total += CampaignService.enqueue_batch(campaign)
    modeladmin.message_user(request, f"{total} destinataires mis en file d'attente.")


@admin.action(description="Exporter les campagnes en CSV")
def export_campaigns_csv(modeladmin, request, queryset):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = "attachment; filename=messaging_campaigns.csv"
    writer = csv.writer(response)
    writer.writerow([
        "id",
        "name",
        "slug",
        "status",
        "scheduled_at",
        "batch_size",
        "dry_run",
        "pending",
        "queued",
        "suppressed",
        "sent",
    ])
    qs = queryset.annotate(
        pending_total=Count("recipients", filter=Q(recipients__status=CampaignRecipient.Status.PENDING)),
        queued_total=Count("recipients", filter=Q(recipients__status=CampaignRecipient.Status.QUEUED)),
        suppressed_total=Count("recipients", filter=Q(recipients__status=CampaignRecipient.Status.SUPPRESSED)),
        sent_total=Count("recipients", filter=Q(recipients__status=CampaignRecipient.Status.SENT)),
    ).order_by("id")
    for campaign in qs:
        writer.writerow([
            campaign.pk,
            campaign.name,
            campaign.slug,
            campaign.status,
            timezone.localtime(campaign.scheduled_at) if campaign.scheduled_at else "",
            campaign.batch_size,
            campaign.dry_run,
            getattr(campaign, "pending_total", 0),
            getattr(campaign, "queued_total", 0),
            getattr(campaign, "suppressed_total", 0),
            getattr(campaign, "sent_total", 0),
        ])
    return response


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "slug",
        "status",
        "scheduled_at",
        "pending_count",
        "queued_count",
        "sent_count",
        "dry_run",
    )
    list_filter = ("status", "dry_run", "locale")
    search_fields = ("name", "slug")
    readonly_fields = ("created_at", "updated_at")
    actions = [schedule_now, start_campaigns, pause_campaigns, complete_campaigns, enqueue_pending, export_campaigns_csv]
    fieldsets = (
        (None, {"fields": ("name", "slug", "status", "dry_run")}),
        ("Contenu", {"fields": ("template_slug", "locale", "subject_override")}),
        ("Planification", {"fields": ("scheduled_at", "batch_size")}),
        ("Métadonnées", {"fields": ("metadata", "created_at", "updated_at")}),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            pending_total=Count("recipients", filter=Q(recipients__status=CampaignRecipient.Status.PENDING)),
            queued_total=Count("recipients", filter=Q(recipients__status=CampaignRecipient.Status.QUEUED)),
            sent_total=Count("recipients", filter=Q(recipients__status=CampaignRecipient.Status.SENT)),
        )

    @admin.display(description="En attente", ordering="pending_total")
    def pending_count(self, obj: Campaign) -> int:
        return getattr(obj, "pending_total", 0)

    @admin.display(description="File", ordering="queued_total")
    def queued_count(self, obj: Campaign) -> int:
        return getattr(obj, "queued_total", 0)

    @admin.display(description="Envoyés", ordering="sent_total")
    def sent_count(self, obj: Campaign) -> int:
        return getattr(obj, "sent_total", 0)


@admin.action(description="Remettre en attente")
def mark_pending(modeladmin, request, queryset):
    updated = queryset.update(status=CampaignRecipient.Status.PENDING, last_enqueued_at=None)
    modeladmin.message_user(request, f"{updated} destinataires remis en attente")


@admin.action(description="Supprimer les destinataires")
def suppress_recipients(modeladmin, request, queryset):
    updated = queryset.update(status=CampaignRecipient.Status.SUPPRESSED, last_enqueued_at=timezone.now())
    modeladmin.message_user(request, f"{updated} destinataires supprimés")


@admin.action(description="Exporter les destinataires en CSV")
def export_recipients_csv(modeladmin, request, queryset):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = "attachment; filename=messaging_recipients.csv"
    writer = csv.writer(response)
    writer.writerow([
        "id",
        "campaign_id",
        "email",
        "status",
        "last_enqueued_at",
        "created_at",
    ])
    for recipient in queryset.select_related("campaign").order_by("id"):
        writer.writerow([
            recipient.pk,
            recipient.campaign_id,
            recipient.email,
            recipient.status,
            timezone.localtime(recipient.last_enqueued_at) if recipient.last_enqueued_at else "",
            timezone.localtime(recipient.created_at) if recipient.created_at else "",
        ])
    return response


@admin.register(CampaignRecipient)
class CampaignRecipientAdmin(admin.ModelAdmin):
    list_display = ("campaign", "email", "status", "last_enqueued_at", "created_at")
    list_filter = ("status", "campaign")
    search_fields = ("email", "campaign__name", "campaign__slug")
    actions = [mark_pending, suppress_recipients, export_recipients_csv]
    readonly_fields = ("campaign", "email", "user", "locale", "status", "last_enqueued_at", "metadata", "created_at", "updated_at")
