from celery import shared_task
from django.db import transaction
from django.utils import timezone
from .models import Lead, LeadEvent
from .constants import LeadStatus
from .audit import log_tasks
from .conf import get_form_policy
from .services import EnrichmentService, ScoringService, RoutingService
from .antispam import dup_fingerprint, dup_recent, normalize_email

@shared_task(name="leads.process_lead", queue="leads", autoretry_for=(Exception,), retry_backoff=True, max_retries=8)
def process_lead(lead_id: int):
    with transaction.atomic():
        try:
            lead = Lead.objects.select_for_update().get(id=lead_id)
        except Lead.DoesNotExist:
            return

        if lead.status != LeadStatus.PENDING:
            return

        # Validation défensive : s'assure que les requis sont OK d'après la politique
        policy = get_form_policy(lead.form_kind, lead.campaign or None)
        fields_pol = (policy.get("fields") or {})
        for fname, spec in fields_pol.items():
            hard_required = spec.get("hard_required")
            if hard_required is None:
                hard_required = bool(spec.get("required") is True)
            if not hard_required:
                continue
            # les clés contextuelles (ex: context.xxx) sont gérées plus bas
            if "." in fname:
                continue

            value = getattr(lead, fname, None)
            if isinstance(value, str):
                value = value.strip()
            is_missing = value in (None, "", [], {})
            if is_missing:
                lead.status = LeadStatus.REJECTED
                lead.reject_reason = "INVALID"
                lead.save(update_fields=["status", "reject_reason", "updated_at"])
                LeadEvent.objects.create(lead=lead, event="rejected", payload={"missing": fname})
                log_tasks.info("lead_rejected_missing lead=%s field=%s", lead.id, fname)
                return

        # Déduplication fenêtre
        # TTL selon kind
        ttl_map = {"email_ebook": 24 * 3600, "contact_full": 2 * 3600, "checkout_intent": 1800}
        fp = dup_fingerprint(
            lead.form_kind,
            email=lead.email,
            phone=lead.phone,
            course_slug=lead.course_slug,
            pack_slug=lead.pack_slug,
        )
        if dup_recent(lead.form_kind, fp, ttl=ttl_map.get(lead.form_kind, 3600)):
            lead.status = LeadStatus.REJECTED
            lead.reject_reason = "DUPLICATE"
            lead.save(update_fields=["status", "reject_reason", "updated_at"])
            LeadEvent.objects.create(lead=lead, event="rejected", payload={"reason": "duplicate"})
            log_tasks.info("lead_duplicate lead=%s", lead.id)
            return

        # Enrichissement + score
        EnrichmentService.normalize(lead)
        lead.score = ScoringService.score(lead)
        lead.enriched_at = timezone.now()
        lead.status = LeadStatus.VALID
        lead.save(update_fields=["score", "enriched_at", "status", "updated_at"])
        LeadEvent.objects.create(lead=lead, event="validated", payload={"score": lead.score})

        try:
            from apps.adsbridge import hooks as adsbridge_hooks
            adsbridge_hooks.record_lead_conversion(lead)
        except Exception:
            log_tasks.exception("lead_adsbridge_hook_failed lead=%s", lead.id)

    # Routage hors lock
    RoutingService.after_validation(lead)
    log_tasks.info("lead_processed lead=%s", lead.id)
