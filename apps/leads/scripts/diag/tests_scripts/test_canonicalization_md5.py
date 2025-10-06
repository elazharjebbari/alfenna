from __future__ import annotations

import hashlib
import json
import logging

from apps.common.runscript_harness import binary_harness
from ._helpers_diag import (
    build_client,
    fetch_home_config,
    ensure_base_fields,
    make_signed_token,
    server_sign,
    md5_body,
)


@binary_harness
def run():
    for logger_name in ('atelier', 'atelier.header', 'atelier.compose', 'atelier.slider'):
        logging.getLogger(logger_name).setLevel(logging.ERROR)
    logs: list[str] = []
    client = build_client(enforce_csrf=False)
    snap = fetch_home_config(client)
    logs.extend(snap.fetch_logs)
    cfg = snap.config
    if not cfg:
        logs.append("config introuvable")
        return {"ok": False, "name": "canonicalization_md5", "duration": 0.0, "logs": logs}

    payload = ensure_base_fields(cfg)
    local_md5 = md5_body(payload)
    logs.append(f"local md5={local_md5}")
    local_token = None
    logs.append(f"local token={local_token}")

    sign_url = cfg.get("sign_url") or "/api/leads/sign/"
    status_sign, body_sign = server_sign(client, sign_url, payload)
    logs.append(f"SIGN status={status_sign} body={body_sign}")
    if status_sign != 200 or "signed_token" not in body_sign:
        return {"ok": False, "name": "canonicalization_md5", "duration": 0.0, "logs": logs}

    server_token = body_sign["signed_token"]
    logs.append(f"server token={server_token}")

    if server_token:
        ts_part = server_token.split(".", 1)[0]
        try:
            local_token = make_signed_token(payload, ts=int(ts_part))
        except ValueError:
            local_token = make_signed_token(payload)
    logs.append(f"local token (server ts)={local_token}")

    variations = {
        "default_json.dumps": json.dumps(payload),
        "sorted_ascii": json.dumps(payload, sort_keys=True, ensure_ascii=True),
        "unsorted_compact": json.dumps(payload, sort_keys=False, separators=(",", ":")),
        "sorted_utf8_spaces": json.dumps(payload, sort_keys=True, separators=(', ', ': '), ensure_ascii=False),
    }
    for name, txt in variations.items():
        digest = hashlib.md5(txt.encode("utf-8")).hexdigest()
        logs.append(f"variant {name}: md5={digest} len={len(txt)}")

    ok = local_token == server_token
    logs.append(f"local==server? {ok}")
    return {"ok": ok, "name": "canonicalization_md5", "duration": 0.0, "logs": logs}
