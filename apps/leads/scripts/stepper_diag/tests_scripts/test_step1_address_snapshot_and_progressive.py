from __future__ import annotations

import time

from ._helpers import apply_step, create_lead_and_session


def run():  # pragma: no cover - executed via runscript
    started = time.time()
    lead, session, ctx = create_lead_and_session()

    step1_data = {
        "full_name": "Client Test",
        "phone": "  +212600000123  ",
        "email": "STEP1@EXAMPLE.COM",
        "address_line1": "Rue Al Amal",
        "address_line2": "Résidence Atlas",
        "city": "Casablanca",
        "state": "Casablanca-Settat",
        "postal_code": "20000",
        "country": "MA",
        "wa_optin": "1",
    }

    lead, session = apply_step(session, ctx, "step1", step1_data)

    snapshot = dict(session.data_snapshot or {})
    lead.refresh_from_db()

    checks = {
        "snapshot_has_address": all(
            key in snapshot
            for key in [
                "address_line1",
                "address_line2",
                "city",
                "state",
                "postal_code",
                "country",
            ]
        ),
        "lead_address": lead.address_line1 == "Rue Al Amal" and lead.city == "Casablanca",
        "lead_email": lead.email == "step1@example.com",
        "lead_phone": lead.phone == "+212600000123",
    }

    ok = all(checks.values())
    duration = round(time.time() - started, 3)
    logs = [
        f"lead_id={lead.id}",
        f"snapshot_keys={sorted(snapshot.keys())}",
        f"checks={checks}",
    ]
    return {"ok": ok, "name": __name__, "duration": duration, "logs": logs}
