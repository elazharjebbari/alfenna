from __future__ import annotations

import time

from ._helpers import apply_step, create_lead_and_session


def run():  # pragma: no cover - executed via runscript
    started = time.time()
    lead, session, ctx = create_lead_and_session()

    apply_step(
        session,
        ctx,
        "step1",
        {
            "full_name": "Client Test",
            "phone": "+212600000789",
            "email": "step3-initial@example.com",
            "address_line1": "Rue 2",
            "city": "Fès",
            "postal_code": "30000",
            "country": "MA",
        },
    )

    apply_step(
        session,
        ctx,
        "step2",
        {
            "pack_slug": "pack-premium",
            "offer_key": "offer_premium",
            "context.complementary_slugs": ["huile-argan"],
        },
    )

    lead, session = apply_step(
        session,
        ctx,
        "step3",
        {
            "payment_mode": "card",
            "email": "step3-final@example.com",
        },
    )

    snapshot = dict(session.data_snapshot or {})
    lead.refresh_from_db()
    context = lead.context or {}

    checks = {
        "payment_mode": lead.payment_mode == "card",
        "email_lower": lead.email == "step3-final@example.com",
        "context_preserved": context.get("complementary_slugs") == ["huile-argan"],
    }

    ok = all(checks.values())
    duration = round(time.time() - started, 3)
    logs = [
        f"lead_id={lead.id}",
        f"snapshot_payment={snapshot.get('payment_mode')}",
        f"context={context}",
        f"checks={checks}",
    ]
    return {"ok": ok, "name": __name__, "duration": duration, "logs": logs}
