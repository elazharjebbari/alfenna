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
        logs.append("config front introuvable (script data-ff-config absent)")
        return {"ok": False, "name": "web_path_e2e", "duration": 0.0, "logs": logs}

    sign_url = cfg.get("sign_url") or "/api/leads/sign/"
    endpoint = cfg.get("endpoint_url") or "/api/leads/collect/"
    payload = ensure_base_fields(cfg)
    logs.append(f"payload initial: {payload}")

    local_token = make_signed_token(payload)
    status_sign, body_sign = server_sign(client, sign_url, payload)
    logs.append(f"SIGN status={status_sign} body={body_sign}")
    if status_sign != 200 or "signed_token" not in body_sign:
        logs.append("impossible d'obtenir un signed_token valide")
        return {"ok": False, "name": "web_path_e2e", "duration": 0.0, "logs": logs}

    payload["signed_token"] = body_sign["signed_token"]
    headers = {
        "X-CSRFToken": get_csrf_token(client),
    }
    idem = new_idem_key("diag-web")
    status_collect, body_collect = post_collect(client, endpoint, payload, idem_key=idem, headers=headers)
    logs.append(f"COLLECT status={status_collect} body={body_collect}")
    logs.append(f"token_local == token_server? {local_token == payload['signed_token']}")

    ok = status_collect in (200, 202) and (body_collect.get("status") in ("pending", "duplicate", None))
    return {"ok": ok, "name": "web_path_e2e", "duration": 0.0, "logs": logs}
