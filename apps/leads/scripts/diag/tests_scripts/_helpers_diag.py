import hashlib
import hmac
import json
import time
import uuid
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from django.conf import settings
from django.test import Client

for logger_name in ('atelier', 'atelier.header', 'atelier.header.debug', 'atelier.compose', 'atelier.slider', 'atelier.slider.debug', 'django.request'):
    logging.getLogger(logger_name).setLevel(logging.ERROR)

SCRIPT_SELECTOR = r'<script[^>]*data-ff-config[^>]*>(?P<json>.*?)</script>'


def build_client(enforce_csrf: bool = True) -> Client:
    return Client(enforce_csrf_checks=enforce_csrf)


@dataclass
class ConfigSnapshot:
    raw_html: str
    config: Dict[str, Any]
    fetch_logs: List[str]


def fetch_home_config(client: Client | None = None) -> ConfigSnapshot:
    import re

    cl = client or build_client()
    fetch_logs: List[str] = []
    resp = cl.get("/", follow=True)
    fetch_logs.append(f"GET / status={resp.status_code}")
    html = resp.content.decode("utf-8", "ignore")
    match = re.search(SCRIPT_SELECTOR, html, re.I | re.S)
    if not match:
        return ConfigSnapshot(raw_html=html, config={}, fetch_logs=fetch_logs + ["config script introuvable"])
    raw_json = match.group("json").strip()
    try:
        cfg = json.loads(raw_json)
    except Exception:
        fetch_logs.append("json.loads direct KO → tentative fallback")
        sanitized = raw_json.replace("&quot;", '"')
        cfg = json.loads(sanitized)
    return ConfigSnapshot(raw_html=html, config=cfg, fetch_logs=fetch_logs)


def canonical_body(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True)


def md5_body(payload: Dict[str, Any]) -> str:
    return hashlib.md5(canonical_body(payload).encode("utf-8")).hexdigest()


def make_signed_token(payload: Dict[str, Any], *, ts: int | None = None) -> str:
    body = dict(payload)
    body.pop("signed_token", None)
    timestamp = ts or int(time.time())
    secret = getattr(settings, "LEADS_SIGNING_SECRET", settings.SECRET_KEY)
    mac = hmac.new(secret.encode("utf-8"), f"{timestamp}.{md5_body(body)}".encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{timestamp}.{mac}"


def server_sign(client: Client, sign_url: str, payload: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    resp = client.post(sign_url, data=payload, content_type="application/json")
    try:
        data = json.loads(resp.content.decode("utf-8"))
    except Exception:
        data = {"raw": resp.content.decode("utf-8", "ignore")}
    return resp.status_code, data


def post_collect(client: Client, endpoint: str, payload: Dict[str, Any], *, idem_key: str, headers: Dict[str, str] | None = None) -> Tuple[int, Dict[str, Any]]:
    headers = headers or {}
    headers.setdefault("X-Idempotency-Key", idem_key)
    resp = client.post(endpoint, data=json.dumps(payload), content_type="application/json", **{f"HTTP_{k.upper().replace('-', '_')}": v for k, v in headers.items()})
    try:
        data = json.loads(resp.content.decode("utf-8"))
    except Exception:
        data = {"raw": resp.content.decode("utf-8", "ignore")}
    return resp.status_code, data


def new_idem_key(prefix: str = "diag") -> str:
    return f"{prefix}-{uuid.uuid4()}"


def ensure_base_fields(cfg: Dict[str, Any]) -> Dict[str, Any]:
    policy_kind = cfg.get("form_kind") or cfg.get("flow_key") or ""
    unique = uuid.uuid4().hex[:8]
    base_payload = {
        "form_kind": "checkout_intent",
        "course_slug": "python-pro",
        "currency": "EUR",
        "email": f"wizard-e2e+{unique}@example.com",
        "accept_terms": True,
        "client_ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "honeypot": "",
    }
    if policy_kind and policy_kind != base_payload["form_kind"]:
        base_payload["form_kind"] = policy_kind
    return base_payload


def get_csrf_token(client: Client) -> str:
    token = client.cookies.get('csrftoken')
    if not token:
        return ''
    return token.value if hasattr(token, 'value') else str(token)
