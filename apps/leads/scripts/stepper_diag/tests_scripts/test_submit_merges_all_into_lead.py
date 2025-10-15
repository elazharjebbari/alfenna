from __future__ import annotations

import time

from apps.leads.submissions import submit_lead_from_flowsession
from ._helpers import apply_step, create_lead_and_session


STEP1_DATA = {
    "full_name": "Client Test",
    "phone": "+212611111111",
    "email": "submit@example.com",
    "address_line1": "Avenue Hassan II",
    "address_line2": "Immeuble Atlas",
    "city": "Marrakech",
    "state": "Marrakech-Safi",
    "postal_code": "40000",
    "country": "MA",
}

STEP2_DATA = {
    "pack_slug": "pack-confort",
    "offer_key": "offer_confort",
    "context.complementary_slugs": ["gommage-sucre"],
}

STEP3_DATA = {
    "payment_mode": "cod",
    "email": "submit-final@example.com",
}


def run():  # pragma: no cover - executed via runscript
    started = time.time()
    lead, session, ctx = create_lead_and_session()

    lead, session = apply_step(session, ctx, "step1", STEP1_DATA)
    lead, session = apply_step(session, ctx, "step2", STEP2_DATA)
    lead, session = apply_step(session, ctx, "step3", STEP3_DATA)

    result = submit_lead_from_flowsession(session)
    lead.refresh_from_db()

    context = lead.context or {}

    checks = {
        "submission_ok": result.ok,
        "address_saved": lead.address_line1 == STEP1_DATA["address_line1"] and lead.city == STEP1_DATA["city"],
        "pack_saved": lead.pack_slug == STEP2_DATA["pack_slug"],
        "payment_mode_saved": lead.payment_mode == STEP3_DATA["payment_mode"],
        "email_saved": lead.email == STEP3_DATA["email"],
        "context_slugs": context.get("complementary_slugs") == STEP2_DATA["context.complementary_slugs"],
    }

    ok = all(checks.values())
    duration = round(time.time() - started, 3)
    logs = [
        f"lead_id={lead.id}",
        f"result={{'ok': {result.ok}, 'reason': '{result.reason}'}}",
        f"context={context}",
        f"checks={checks}",
    ]
    return {"ok": ok, "name": __name__, "duration": duration, "logs": logs}
