from __future__ import annotations
import json
import logging
from typing import Any, Dict, Optional

from django.conf import settings
from django.urls import NoReverseMatch, reverse

from apps.flowforms.conf.loader import get_flow

log = logging.getLogger("flowforms.services")

_UI_DEFAULTS = {
    "label_email": "Votre e-mail",
    "label_first_name": "Votre prénom (facultatif)",
    "cta_next": "Suivant",
    "cta_submit": "Envoyer",
    "error_generic": "Une erreur est survenue.",
    "error_rate_limit": "Trop de tentatives, réessayez plus tard.",
}

def _safe_reverse(urlname: str, *, default: Optional[str] = None) -> Optional[str]:
    try:
        return reverse(urlname)
    except NoReverseMatch:
        log.warning("Reverse failed for urlname=%s", urlname)
        return default

def _extract_marketing_context(request) -> Dict[str, Any]:
    q = request.GET
    return {
        "utm_source": q.get("utm_source"),
        "utm_medium": q.get("utm_medium"),
        "utm_campaign": q.get("utm_campaign"),
        "utm_term": q.get("utm_term"),
        "utm_content": q.get("utm_content"),
        "ref": q.get("ref"),
    }

def build_shell_context(request, *, flow_key: Optional[str], overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Construit le JSON de config consommé par le runtime front + assets.
    TOLÉRANT: remplit les defaults même si pages ne fournit rien.
    """
    overrides = overrides or {}
    fk = (flow_key or "").strip() or getattr(settings, "FLOWFORMS_DEFAULT_FLOW_KEY", "checkout_intent_flow")

    # kind (depuis YAML) avec fallback
    try:
        flow_cfg = get_flow(fk)
        kind = flow_cfg.get("kind") or "checkout_intent"
    except Exception:
        log.warning("Flow '%s' introuvable; fallback kind=checkout_intent", fk)
        kind = "checkout_intent"

    # endpoints
    endpoint_url = overrides.get("endpoint_url") or _safe_reverse(
        getattr(settings, "FLOWFORMS_ENDPOINT_COLLECT_URLNAME", "leads:collect"),
        default="/leads/collect/",
    )

    require_signed = bool(overrides.get("require_signed_token",
                                        getattr(settings, "FLOWFORMS_REQUIRE_SIGNED", False)))
    sign_url = None
    if require_signed:
        sign_url = overrides.get("sign_url") or _safe_reverse(
            getattr(settings, "FLOWFORMS_SIGN_URLNAME", "leads:sign"),
            default=None,
        )

    # UI
    ui = dict(_UI_DEFAULTS)
    ui_override = overrides.get("ui") or {}
    ui.update({k: v for k, v in ui_override.items() if v})

    cfg: Dict[str, Any] = {
        "flow_key": fk,
        "form_kind": kind,
        "endpoint_url": endpoint_url,
        "require_signed_token": require_signed,
        "sign_url": sign_url,
        "context": _extract_marketing_context(request),
        "ui": ui,
    }

    assets = {
        "head": [],
        "css": [],
        "js": [
            "/static/js/flowforms.runtime.js",
            "/static/site/flowforms_tracking.js",
        ],
        "vendors": [],
    }

    # Titre/sous-titre par défaut (peuvent être surchargés par le slot)
    shell_title = "Accédez à la formation"
    shell_sub = "Entrez votre email pour démarrer."

    return {
        "config_dict": cfg,                     # dict brut
        "config_json": json.dumps(cfg),         # JSON string (pour <script data-ff-config>)
        "assets": assets,
        "title_html": shell_title,
        "subtitle_html": shell_sub,
    }
