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
            "phone": "+212600000456",
            "email": "step2@example.com",
            "address_line1": "Rue 1",
            "city": "Rabat",
            "postal_code": "10000",
            "country": "MA",
        },
    )

    complementary = ["bougie-massage-hydratante"]
    lead, session = apply_step(
        session,
        ctx,
        "step2",
        {
            "pack_slug": "pack-complet",
            "offer_key": "offer_duo",
            "context.complementary_slugs": complementary,
        },
    )

    snapshot = dict(session.data_snapshot or {})
    lead.refresh_from_db()
    context = lead.context or {}

    checks = {
        "snapshot_pack": snapshot.get("pack_slug") == "pack-complet",
        "lead_pack": lead.pack_slug == "pack-complet",
        "context_slugs": context.get("complementary_slugs") == complementary,
    }

    ok = all(checks.values())
    duration = round(time.time() - started, 3)
    logs = [
        f"lead_id={lead.id}",
        f"snapshot_keys={sorted(snapshot.keys())}",
        f"context={context}",
        f"checks={checks}",
    ]
    return {"ok": ok, "name": __name__, "duration": duration, "logs": logs}
