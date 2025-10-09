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
            "full_name": "Client A",
            "phone": "+212622222222",
            "email": "prevnext@example.com",
            "address_line1": "Boulevard Med V",
            "city": "Tanger",
            "postal_code": "90000",
            "country": "MA",
        },
    )

    apply_step(
        session,
        ctx,
        "step2",
        {
            "pack_slug": "pack-duo",
            "offer_key": "offer_duo",
            "context.complementary_slugs": ["savon-noir"],
        },
    )

    lead, session = apply_step(
        session,
        ctx,
        "step1",
        {
            "full_name": "Client B",
            "phone": "+212699999999",
            "email": "prevnext-updated@example.com",
        },
    )

    snapshot = dict(session.data_snapshot or {})
    lead.refresh_from_db()

    checks = {
        "step2_data_kept": snapshot.get("pack_slug") == "pack-duo",
        "context_kept": (lead.context or {}).get("complementary_slugs") == ["savon-noir"],
        "step1_updated": lead.full_name == "Client B" and lead.phone == "+212699999999",
    }

    ok = all(checks.values())
    duration = round(time.time() - started, 3)
    logs = [
        f"lead_id={lead.id}",
        f"snapshot_keys={sorted(snapshot.keys())}",
        f"checks={checks}",
    ]
    return {"ok": ok, "name": __name__, "duration": duration, "logs": logs}
