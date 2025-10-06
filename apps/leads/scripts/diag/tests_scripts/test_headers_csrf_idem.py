from __future__ import annotations

import json

from apps.common.runscript_harness import binary_harness
from ._helpers_diag import (
    build_client,
    fetch_home_config,
    ensure_base_fields,
    server_sign,
    post_collect,
    new_idem_key,
    get_csrf_token,
)


def _manual_post(client, endpoint: str, payload: dict) -> tuple[int, dict]:
    resp = client.post(endpoint, data=json.dumps(payload), content_type="application/json")
    try:
        data = json.loads(resp.content.decode("utf-8"))
    except Exception:
        data = {"raw": resp.content.decode("utf-8", "ignore")}
    return resp.status_code, data


@binary_harness
def run():
    logs: list[str] = []
    client = build_client(enforce_csrf=True)
    snap = fetch_home_config(client)
    logs.extend(snap.fetch_logs)
    cfg = snap.config
    if not cfg:
        logs.append("config front introuvable")
        return {"ok": False, "name": "headers_csrf_idem", "duration": 0.0, "logs": logs}

    sign_url = cfg.get("sign_url") or "/api/leads/sign/"
    endpoint = cfg.get("endpoint_url") or "/api/leads/collect/"
    payload = ensure_base_fields(cfg)

    status_sign, body_sign = server_sign(client, sign_url, payload)
    logs.append(f"SIGN status={status_sign} body={body_sign}")
    if status_sign != 200 or "signed_token" not in body_sign:
        return {"ok": False, "name": "headers_csrf_idem", "duration": 0.0, "logs": logs + ["signature serveur absente"]}

    payload["signed_token"] = body_sign["signed_token"]
    csrf = get_csrf_token(client)

    scenarios = [
        ("baseline", csrf, new_idem_key("hdr"), True),
        ("missing_csrf", "", new_idem_key("hdr"), False),
        ("invalid_csrf", "bogus-token", new_idem_key("hdr"), False),
        ("missing_idempotency", csrf, "", False),
        ("duplicate_idempotency", csrf, "reuse-key", True),
    ]

    results: list[str] = []
    baseline_ok = False

    # First call for duplicate scenario uses unique key; second call reuses it
    duplicate_body = None
    for name, csrf_token, idem_key, expect_success in scenarios:
        headers = {}
        if csrf_token:
            headers["X-CSRFToken"] = csrf_token
        if name == "missing_idempotency":
            status, body = _manual_post(client, endpoint, payload)
        else:
            status, body = post_collect(
                client,
                endpoint,
                payload,
                idem_key=idem_key,
                headers=headers,
            )
        if name == "duplicate_idempotency" and duplicate_body is None:
            duplicate_body = (status, body)
            # Rejoue immédiatement avec la même clé
            status, body = post_collect(
                client,
                endpoint,
                payload,
                idem_key=idem_key,
                headers=headers,
            )
            results.append(f"duplicate_idempotency_first: {duplicate_body}")
        results.append(f"{name}: status={status} body={body}")
        if name == "baseline":
            baseline_ok = status in (200, 202)

    logs.extend(results)
    ok = baseline_ok
    return {"ok": ok, "name": "headers_csrf_idem", "duration": 0.0, "logs": logs}
