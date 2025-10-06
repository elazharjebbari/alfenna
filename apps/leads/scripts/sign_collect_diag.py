from __future__ import annotations

import json
from uuid import uuid4

import django
from django.test import Client


def run() -> None:
    django.setup()
    client = Client()

    final_body = {
        "form_kind": "product_lead",
        "full_name": "Diag User",
        "phone": "+212600000002",
        "address": "Casablanca",
        "offer_key": "duo",
        "payment_method": "cod",
        "consent": True,
        "context": {"utm_source": "diag"},
    }

    sign_response = client.post(
        "/api/leads/sign/",
        data=json.dumps({"payload": final_body}),
        content_type="application/json",
    )
    print("[diag] sign status:", sign_response.status_code, sign_response.content.decode())
    if sign_response.status_code >= 400:
        return

    signed_token = sign_response.json().get("signed_token")
    body_to_collect = dict(final_body, signed_token=signed_token)

    collect_response = client.post(
        "/api/leads/collect/",
        data=json.dumps(body_to_collect),
        content_type="application/json",
        HTTP_X_IDEMPOTENCY_KEY=f"diag-{uuid4().hex}",
    )
    print("[diag] collect status:", collect_response.status_code, collect_response.content.decode())


if __name__ == "__main__":
    run()
