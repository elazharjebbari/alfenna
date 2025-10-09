from __future__ import annotations

import time

from ._helpers import apply_step, create_lead_and_session


def run():  # pragma: no cover - executed via runscript
    started = time.time()
    lead, session, ctx = create_lead_and_session()

    step1_payload = {
        "full_name": "Audit Stepper",
        "email": "audit@example.com",
        "phone": "\n +212700000000 \n",
        "address_line1": "12 rue Ibn Sina",
        "address_line2": "Résidence Atlas",
        "city": "Rabat",
        "state": "Rabat-Salé",
        "postal_code": "10000",
        "country": "MA",
    }
    lead, session = apply_step(session, ctx, "step1", step1_payload)
    lead.refresh_from_db()

    checks_step1 = {
        "email": lead.email == "audit@example.com",
        "phone": lead.phone == "+212700000000",
        "address_line1": lead.address_line1 == "12 rue Ibn Sina",
        "city": lead.city == "Rabat",
        "postal_code": lead.postal_code == "10000",
        "country": lead.country == "MA",
    }

    step2_payload = {
        "pack_slug": "pack-duo",
        "offer_key": "pack-duo",
        "context.complementary_slugs": ["serum-vitamine-c", "bougie-massage"],
        "context.quantity": "2",
        "context.promotion_selected": "promo-launch",
    }
    lead, session = apply_step(session, ctx, "step2", step2_payload)
    lead.refresh_from_db()
    context = lead.context or {}

    checks_step2 = {
        "pack_slug": lead.pack_slug == "pack-duo",
        "complementaries": context.get("complementary_slugs") == [
            "serum-vitamine-c",
            "bougie-massage",
        ],
        "quantity": context.get("quantity") == "2",
        "promotion": context.get("promotion_selected") == "promo-launch",
    }

    step3_payload = {
        "payment_mode": "card",
        "email": "audit-final@example.com",
    }
    lead, session = apply_step(session, ctx, "step3", step3_payload)
    lead.refresh_from_db()

    checks_step3 = {
        "payment_mode": lead.payment_mode == "card",
        "email": lead.email == "audit-final@example.com",
    }

    ok = all(list(checks_step1.values()) + list(checks_step2.values()) + list(checks_step3.values()))
    duration = round(time.time() - started, 3)
    logs = [
        f"lead_id={lead.id}",
        f"context={context}",
        f"checks_step1={checks_step1}",
        f"checks_step2={checks_step2}",
        f"checks_step3={checks_step3}",
    ]
    return {"ok": ok, "name": __name__, "duration": duration, "logs": logs}
