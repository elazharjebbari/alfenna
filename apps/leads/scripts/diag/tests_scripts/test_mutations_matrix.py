from __future__ import annotations

import copy

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

SCENARIOS = [
    ("baseline", lambda p: None),
    ("trim_email", lambda p: p.update(email=p["email"] + " ")),
    ("bool_as_string", lambda p: p.update(accept_terms="true")),
    ("drop_course_slug", lambda p: p.pop("course_slug", None)),
    ("extra_field", lambda p: p.update(extra_field="diagnostic")),
    ("unicode_email", lambda p: p.update(email="élève@example.com")),
]


@binary_harness
def run():
    client = build_client(enforce_csrf=True)
    snap = fetch_home_config(client)
    logs = list(snap.fetch_logs)
    cfg = snap.config
    if not cfg:
        logs.append("config introuvable")
        return {"ok": False, "name": "mutations_matrix", "duration": 0.0, "logs": logs}

    sign_url = cfg.get("sign_url") or "/api/leads/sign/"
    endpoint = cfg.get("endpoint_url") or "/api/leads/collect/"
    base_payload = ensure_base_fields(cfg)

    status_sign, body_sign = server_sign(client, sign_url, base_payload)
    logs.append(f"SIGN status={status_sign} body={body_sign}")
    if status_sign != 200 or "signed_token" not in body_sign:
        logs.append("signature serveur échouée")
        return {"ok": False, "name": "mutations_matrix", "duration": 0.0, "logs": logs}

    headers = {"X-CSRFToken": get_csrf_token(client)}
    results: list[str] = []
    baseline_ok = False

    for name, mutator in SCENARIOS:
        payload = copy.deepcopy(base_payload)
        payload["signed_token"] = body_sign["signed_token"]
        mutator(payload)
        status_collect, body_collect = post_collect(
            client,
            endpoint,
            payload,
            idem_key=new_idem_key(f"mut-{name}"),
            headers=headers,
        )
        line = f"{name}: {status_collect} {body_collect}"
        results.append(line)
        if name == "baseline":
            baseline_ok = status_collect in (200, 202)

    logs.extend(results)
    ok = baseline_ok
    return {"ok": ok, "name": "mutations_matrix", "duration": 0.0, "logs": logs}
