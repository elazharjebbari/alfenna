# apps/flowforms/engine/storage.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any, Optional, Tuple, List

from django.db import transaction
from django.utils import timezone

from apps.leads.models import Lead
from apps.leads.constants import LeadStatus
from apps.leads.submissions import _ALLOWED_LEAD_FIELDS as ALLOWED_LEAD_FIELDS
from apps.flowforms.models import FlowSession, FlowStatus

DEFAULT_LOOKUP_FIELDS = ("email", "phone", "course_slug")

@dataclass
class FlowContext:
    flow_key: str
    form_kind: str  # ex: "checkout_intent"
    lookup_fields: Tuple[str, ...] = DEFAULT_LOOKUP_FIELDS

# -----------------------------
# Helpers
# -----------------------------
def _ensure_session_key(request) -> str:
    if not request.session.session_key:
        request.session.save()
    return request.session.session_key

def _lead_lookup(form_kind: str, data: Dict[str, Any], lookup_fields: Tuple[str, ...]) -> Optional[Lead]:
    """
    Stratégie par défaut :
      - cherche un Lead du même form_kind
      - en priorité par email (normalisé), sinon phone, sinon course_slug
    """
    qs = Lead.objects.filter(form_kind=form_kind).order_by("-created_at")
    email = (data.get("email") or "").strip().lower()
    phone = (data.get("phone") or "").strip()
    slug = (data.get("course_slug") or "").strip()

    if "email" in lookup_fields and email:
        m = qs.filter(email=email).first()
        if m:
            return m
    if "phone" in lookup_fields and phone:
        m = qs.filter(phone=phone).first()
        if m:
            return m
    if "course_slug" in lookup_fields and slug:
        m = qs.filter(course_slug=slug).first()
        if m:
            return m
    return None

def _make_idempotency_key(flow_key: str, session_key: str) -> str:
    return f"flow:{flow_key}:{session_key}"

# -----------------------------
# Public API
# -----------------------------
def get_or_create_session(request, ctx: FlowContext) -> FlowSession:
    """
    Récupère ou crée une FlowSession (clé = flow_key + session_key).
    """
    sk = _ensure_session_key(request)
    fs, _created = FlowSession.objects.get_or_create(
        flow_key=ctx.flow_key,
        session_key=sk,
        defaults={
            "status": FlowStatus.ACTIVE,
            "data_snapshot": {},
        },
    )
    # Keep last_touch fresh
    fs.touch()
    return fs

@transaction.atomic
def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return False


def _merge_lead_progressively(lead: Lead, cleaned_data: Dict[str, Any]) -> None:
    if not lead:
        return

    updated_fields: List[str] = []

    for field in ALLOWED_LEAD_FIELDS:
        if field not in cleaned_data:
            continue
        value = cleaned_data[field]
        if _is_empty(value):
            continue
        if isinstance(value, str):
            value = value.strip()
        if getattr(lead, field, None) != value:
            setattr(lead, field, value)
            updated_fields.append(field)

    if "email" in updated_fields:
        normalised = (lead.email or "").strip().lower()
        if lead.email != normalised:
            lead.email = normalised
    if "phone" in updated_fields:
        normalised_phone = (lead.phone or "").strip()
        if lead.phone != normalised_phone:
            lead.phone = normalised_phone

    context_payload = dict(lead.context or {})
    context_changed = False
    for key, value in cleaned_data.items():
        if not isinstance(key, str) or not key.startswith("context."):
            continue
        sub_key = key.split(".", 1)[1].strip()
        if not sub_key or _is_empty(value):
            continue
        if context_payload.get(sub_key) != value:
            context_payload[sub_key] = value
            context_changed = True

    if context_changed:
        lead.context = context_payload
        updated_fields.append("context")

    if updated_fields:
        update_fields = list(dict.fromkeys(updated_fields))
        if "updated_at" not in update_fields:
            update_fields.append("updated_at")
        lead.save(update_fields=update_fields)


def persist_step(
    *,
    flowsession: FlowSession,
    ctx: FlowContext,
    step_key: str,
    cleaned_data: Dict[str, Any],
) -> Tuple[Lead, FlowSession]:
    """
    Persiste les données validées d’une step :
      - Merge/attach lead existant (lookup) OU création d’un lead PENDING minimal
      - Applique les valeurs (via builder.save côté formulaire)
      - Met à jour FlowSession (current_step, snapshot, last_touch_at)
    """
    # 0) lookup lead si inconnu
    lead = flowsession.lead
    if lead is None:
        existing = _lead_lookup(ctx.form_kind, cleaned_data, ctx.lookup_fields)
        if existing:
            lead = existing
        else:
            # Création minimaliste (aucun routage/queue ici)
            lead = Lead.objects.create(
                form_kind=ctx.form_kind,
                email=(cleaned_data.get("email") or "").strip().lower(),
                phone=cleaned_data.get("phone") or "",
                course_slug=cleaned_data.get("course_slug") or "",
                idempotency_key=_make_idempotency_key(flowsession.flow_key, flowsession.session_key),
                status=LeadStatus.PENDING,
            )
        flowsession.lead = lead

    # 1) snapshot : merge cumulatif (sans écraser volontairement les anciennes valeurs non fournies)
    snapshot = dict(flowsession.data_snapshot or {})
    for k, v in cleaned_data.items():
        snapshot[k] = v

    # 2) update FlowSession
    flowsession.current_step = step_key
    flowsession.data_snapshot = snapshot
    flowsession.status = FlowStatus.ACTIVE
    flowsession.last_touch_at = timezone.now()
    flowsession.save(update_fields=["current_step", "data_snapshot", "status", "last_touch_at", "updated_at", "lead"])

    _merge_lead_progressively(lead, cleaned_data)

    return lead, flowsession
