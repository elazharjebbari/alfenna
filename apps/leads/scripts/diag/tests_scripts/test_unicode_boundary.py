from __future__ import annotations

from apps.common.runscript_harness import binary_harness
from ._helpers_diag import (
    build_client,
    fetch_home_config,
    ensure_base_fields,
    make_signed_token,
    server_sign,
    post_collect,
    new_idem_key,
    get_csrf_token,
)


@binary_harness
def run():
    logs: list[str] = []
    client = build_client(enforce_csrf=True)
    snap = fetch_home_config(client)
    logs.extend(snap.fetch_logs)
    cfg = snap.config
    if not cfg:
        logs.append("config introuvable")
        return {"ok": False, "name": "unicode_boundary", "duration": 0.0, "logs": logs}

    payload = ensure_base_fields(cfg)
    payload.update({
        "email": "élève😊@example.com",
        "first_name": "Élodie 😊",
        "last_name": "Łukasz",
        "newsletter_optin": True,
    })

    local_token = make_signed_token(payload)
    logs.append(f"token local={local_token}")

    sign_url = cfg.get("sign_url") or "/api/leads/sign/"
    endpoint = cfg.get("endpoint_url") or "/api/leads/collect/"

    status_sign, body_sign = server_sign(client, sign_url, payload)
    logs.append(f"SIGN status={status_sign} body={body_sign}")
    if status_sign != 200 or "signed_token" not in body_sign:
        return {"ok": False, "name": "unicode_boundary", "duration": 0.0, "logs": logs}

    payload["signed_token"] = body_sign["signed_token"]
    headers = {"X-CSRFToken": get_csrf_token(client)}
    status_collect, body_collect = post_collect(
        client,
        endpoint,
        payload,
        idem_key=new_idem_key("unicode"),
        headers=headers,
    )
    logs.append(f"COLLECT status={status_collect} body={body_collect}")
    logs.append(f"token local == server? {local_token == payload['signed_token']}")

    variant_payload = dict(payload)
    variant_payload["newsletter_optin"] = "true"
    status_variant, body_variant = post_collect(
        client,
        endpoint,
        variant_payload,
        idem_key=new_idem_key("unicode-var"),
        headers=headers,
    )
    logs.append(f"variant bool string status={status_variant} body={body_variant}")

    ok = status_collect in (200, 202)
    return {"ok": ok, "name": "unicode_boundary", "duration": 0.0, "logs": logs}
