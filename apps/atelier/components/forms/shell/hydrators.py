# apps/atelier/components/forms/shell/hydrators.py
from __future__ import annotations
import json
from typing import Dict, Any, Optional
from django.conf import settings
from django.template.loader import render_to_string
from django.urls import reverse, NoReverseMatch

def _endpoint_url() -> str:
    try:
        urlname = getattr(settings, "FLOWFORMS_ENDPOINT_COLLECT_URLNAME", "leads:collect")
        return reverse(urlname)
    except NoReverseMatch:
        return "/api/leads/collect/"

def _default_flow_key() -> str:
    return getattr(settings, "FLOWFORMS_DEFAULT_FLOW_KEY", "checkout_intent_flow")

def _compose_enabled() -> bool:
    # Compat avec les deux flags utilisés dans les tests
    return bool(
        getattr(settings, "FLOWFORMS_USE_CHILD_COMPOSE", False)
        or getattr(settings, "FLOWFORMS_COMPONENT_ENABLED", False)
    )

def _make_config_json(flow_key: str) -> str:
    cfg = {
        "flow_key": flow_key,
        "form_kind": "email_ebook",
        "endpoint_url": _endpoint_url(),
        "require_signed_token": bool(getattr(settings, "FLOWFORMS_REQUIRE_SIGNED", False)),
        "sign_url": reverse(getattr(settings, "FLOWFORMS_SIGN_URLNAME", "flowforms:sign"))
                    if getattr(settings, "FLOWFORMS_REQUIRE_SIGNED", False) else None,
        "ui": {"next": "Continuer", "prev": "Retour", "submit": "Envoyer"},
        "context": {},
    }
    cfg = {k: v for k, v in cfg.items() if v is not None}
    return json.dumps(cfg, ensure_ascii=False)

def _backend_config():
    bc = {
        "endpoint_url": _endpoint_url(),
        "require_signed_token": bool(getattr(settings, "FLOWFORMS_REQUIRE_SIGNED", False)),
    }
    if bc["require_signed_token"]:
        try:
            bc["sign_url"] = reverse(getattr(settings, "FLOWFORMS_SIGN_URLNAME", "leads:sign"))
        except NoReverseMatch:
            pass
    return bc

def _render_wizard(config_json: str, request) -> str:
    # On rend le même template pour compose et legacy → parité maximale
    return render_to_string(
        "components/forms/wizard.html",
        {"config_json": config_json},
        request=request,
    )

def hydrate(request, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    params = params or {}
    flow_key = params.get("flow_key") or _default_flow_key()
    config_json = params.get("config_json") or _make_config_json(flow_key)
    compose_on = _compose_enabled()

    ctx: Dict[str, Any] = {
        # Décor UX
        "display": params.get("display", "inline"),
        "title_html": params.get("title_html"),
        "subtitle_html": params.get("subtitle_html"),
        "cta_label": params.get("cta_label"),
        # Flag lu par le template parent
        "use_child_compose": compose_on,
        # Contrat V3 (parents → child)
        "child": {
            "flow_key": flow_key,
            "config_json": config_json,
            "backend_config": _backend_config(),
            "ui_texts": {"next": "Continuer"},
        },
    }

    if compose_on:
        # OFFICIEL: compose → fournir le fragment enfant
        ctx["children"] = {"wizard": _render_wizard(config_json, request)}
        # SHADOW (non rendu) pour parité
        ctx["__shadow_legacy"] = {
            "wizard_html": _render_wizard(config_json, request),
            "flow_key": flow_key,
        }
    else:
        # LEGACY affiché (pour compat)
        ctx["wizard_html"] = _render_wizard(config_json, request)

    # Anti-pollution: pas de wizard_ctx
    return ctx
