from __future__ import annotations

from typing import Any, Dict, Tuple
from uuid import uuid4

from apps.flowforms.engine.storage import FlowContext, persist_step
from apps.flowforms.models import FlowSession
from apps.leads.models import Lead

FLOW_KEY = "checkout_intent_flow"
FORM_KIND = "checkout_intent"


def create_lead_and_session() -> Tuple[Lead, FlowSession, FlowContext]:
    lead = Lead.objects.create(
        form_kind=FORM_KIND,
        idempotency_key=f"stepper-test:{uuid4()}",
    )
    session = FlowSession.objects.create(
        flow_key=FLOW_KEY,
        session_key=f"sess-{uuid4()}",
        lead=lead,
    )
    ctx = FlowContext(flow_key=FLOW_KEY, form_kind=FORM_KIND)
    return lead, session, ctx


def apply_step(session: FlowSession, ctx: FlowContext, step_key: str, cleaned_data: Dict[str, Any]) -> Tuple[Lead, FlowSession]:
    lead, fs = persist_step(flowsession=session, ctx=ctx, step_key=step_key, cleaned_data=cleaned_data)
    lead.refresh_from_db()
    fs.refresh_from_db()
    return lead, fs
