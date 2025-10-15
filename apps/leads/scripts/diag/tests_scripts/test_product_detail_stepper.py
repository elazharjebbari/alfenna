from __future__ import annotations

import time

from django.utils import timezone
from uuid import uuid4

from apps.flowforms.models import FlowSession, FlowStatus
from apps.leads.constants import LeadStatus
from apps.leads.models import Lead
from apps.leads.submissions import submit_lead_from_flowsession


FLOW_KEY = "checkout_intent_flow"
FORM_KIND = "checkout_intent"


def run():  # pragma: no cover - executed via runscript
    started = time.time()
    logs = []

    lead = Lead.objects.create(
        form_kind=FORM_KIND,
        email="old@example.com",
        status=LeadStatus.PENDING,
        page_path="/produits/pack-cosmetique-naturel/",
        locale="fr",
        idempotency_key=f"diag-stepper:{uuid4().hex}",
    )
    logs.append(f"lead_seed id={lead.id}")

    snapshot = {
        "pack_slug": "pack-cosmetique-naturel",
        "postal_code": "10000",
        "country": "MA",
        "address_line1": "18 Rue Patrice Lumumba",
        "city": "Rabat",
        "currency": "MAD",
        "context.pack.slug": "pack-cosmetique-naturel",
        "context.pack.title": "Pack Cosmétique Naturel",
        "context.pack.price": 199.0,
        "context.pack.currency": "MAD",
        "context.addon.slug": "bougie-massage-hydratante",
        "context.addon.title": "Bougie de massage hydratante",
        "context.addon.price": 40.0,
        "context.addon.currency": "MAD",
        "context.payment.method": "cod",
        "context.complementary_slugs": ["bougie-massage-hydratante"],
        "context.checkout.subtotal": 239.0,
        "context.checkout.discount": 0.0,
        "context.checkout.total": 239.0,
        "context.checkout.currency": "MAD",
        "context.checkout.quantity": 1,
        "context.checkout.amount_minor": 23900,
        "payment_mode": "cod",
        "client_ts": timezone.now().isoformat(),
        "accept_terms": True,
    }

    flowsession = FlowSession.objects.create(
        flow_key=FLOW_KEY,
        session_key=f"diag-sess-{uuid4().hex[:10]}",
        lead=lead,
        data_snapshot=snapshot,
        status=FlowStatus.ACTIVE,
    )

    result = submit_lead_from_flowsession(flowsession)
    lead.refresh_from_db()

    context = lead.context or {}
    pack = context.get("pack") or {}
    addon = context.get("addon") or {}
    payment = context.get("payment") or {}

    checks = {
        "submission_ok": result.ok,
        "postal_code_mapped": lead.postal_code == snapshot["postal_code"],
        "country_mapped": lead.country == snapshot["country"],
        "pack_slug_mapped": lead.pack_slug == snapshot["pack_slug"],
        "payment_mode_mapped": lead.payment_mode == snapshot["payment_mode"],
        "pack_slug_context": pack.get("slug") == snapshot["context.pack.slug"],
        "addon_slug_context": addon.get("slug") == snapshot["context.addon.slug"],
        "payment_method_context": payment.get("method") == snapshot["context.payment.method"],
        "complementary_slugs": context.get("complementary_slugs") == snapshot["context.complementary_slugs"],
        "checkout_total": context.get("checkout", {}).get("total") == snapshot["context.checkout.total"],
    }

    ok = all(checks.values())

    logs.extend([
        f"submit={{'ok': {result.ok}, 'reason': '{result.reason}'}}",
        f"context={context}",
        f"checks={checks}",
    ])

    return {
        "ok": ok,
        "name": "test_product_detail_stepper",
        "duration": round(time.time() - started, 3),
        "logs": logs,
    }
