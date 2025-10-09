from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict, Any

from django.db import transaction
from django.utils import timezone

from apps.flowforms.models import FlowSession  # type: ignore
from .models import Lead, LeadEvent, LeadSubmissionLog
from .constants import LeadStatus
from .audit import log_submit
from .tasks import process_lead

# Champs Lead mappables depuis snapshot (hors context.*)
_ALLOWED_LEAD_FIELDS = {
    "email", "first_name", "last_name", "full_name", "phone",
    "address_line1", "address_line2", "city", "state", "postal_code", "country",
    "course_slug", "pack_slug", "currency", "payment_mode", "coupon_code",
    "billing_address_line1", "billing_address_line2", "billing_city", "billing_state",
    "billing_postal_code", "billing_country", "company_name", "tax_id_type", "tax_id",
    "save_customer", "accept_terms", "invoice_language",
    "ebook_id", "newsletter_optin", "consent",
    "campaign", "source", "utm_source", "utm_medium", "utm_campaign",
    "client_ts", "locale", "ab_variant",
}

@dataclass
class SubmitResult:
    ok: bool
    lead_id: int
    flowsession_id: int
    log_id: Optional[int] = None
    reason: str = ""

def _merge_context(lead: Lead, snapshot: Dict[str, Any]) -> None:
    ctx = dict(lead.context or {})
    for k, v in snapshot.items():
        if isinstance(k, str) and k.startswith("context."):
            key = k.split(".", 1)[1]
            ctx[key] = v
    lead.context = ctx

def _apply_fields(lead: Lead, snapshot: Dict[str, Any]) -> None:
    for k in _ALLOWED_LEAD_FIELDS:
        if k in snapshot:
            setattr(lead, k, snapshot[k])
    lead.email = (lead.email or "").strip().lower()
    lead.phone = (lead.phone or "").strip()
    if lead.consent and not lead.consent_at:
        lead.consent_at = timezone.now()

def _ensure_submission_log(lead: Lead, fs: FlowSession, snapshot: Dict[str, Any]) -> LeadSubmissionLog:
    log, created = LeadSubmissionLog.objects.get_or_create(
        lead=lead,
        flow_key=fs.flow_key,
        session_key=fs.session_key,
        step="",
        defaults={"status": LeadStatus.PENDING, "payload": snapshot, "attempt_count": 0},
    )
    if not created and not log.payload:
        log.payload = snapshot
    return log

@transaction.atomic
def submit_lead_from_flowsession(fs: FlowSession) -> SubmitResult:
    """
    Finalise un flow:
      - Map snapshot -> Lead (champs autorisés + context.*)
      - Journalise la soumission (idempotent par (lead, flow, session))
      - Déclenche le traitement async (process_lead), idempotent côté task (PENDING only)
    """
    try:
        lead = fs.lead
        if not lead:
            return SubmitResult(ok=False, lead_id=0, flowsession_id=fs.id, reason="NO_LEAD")

        snapshot = dict(fs.data_snapshot or {})
        log = _ensure_submission_log(lead, fs, snapshot)
        log.attempt_count += 1
        log.save(update_fields=["attempt_count", "updated_at"])

        # Si déjà validé côté soumission, on skippe (VALID = success)
        if log.status == LeadStatus.VALID:
            log_submit.info("submit_skip_already_valid lead=%s fs=%s", lead.id, fs.id)
            return SubmitResult(ok=True, lead_id=lead.id, flowsession_id=fs.id, log_id=log.id, reason="ALREADY_SUBMITTED")

        # Appliquer snapshot -> lead
        _apply_fields(lead, snapshot)
        _merge_context(lead, snapshot)
        lead.save()

        LeadEvent.objects.create(
            lead=lead,
            event="flow_submitted",
            payload={"flow_key": fs.flow_key, "session_key": fs.session_key},
        )

        # Traitement asynchrone
        process_lead.delay(lead.id)

        # Marque la soumission comme VALID (succès de la soumission, pas la validation métier)
        log.status = LeadStatus.VALID
        log.message = "submitted"
        log.save(update_fields=["status", "message", "updated_at"])
        log_submit.info("submit_valid lead=%s fs=%s", lead.id, fs.id)

        return SubmitResult(ok=True, lead_id=lead.id, flowsession_id=fs.id, log_id=log.id)

    except Exception as e:
        try:
            if fs.lead_id:
                log = _ensure_submission_log(fs.lead, fs, fs.data_snapshot or {})
                log.status = LeadStatus.FAILED_TEMP  # échec technique de soumission
                log.last_error = str(e)
                log.save(update_fields=["status", "last_error", "updated_at"])
        except Exception:
            pass
        log_submit.exception("submit_exception fs=%s", fs.id)
        return SubmitResult(ok=False, lead_id=fs.lead_id or 0, flowsession_id=fs.id, reason="EXCEPTION")
