"""Hydrators for chatbot Atelier components."""

from __future__ import annotations

from typing import Any, Dict, List

from django.conf import settings
from django.utils.html import escape


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _as_str(value: Any, default: str = "") -> str:
    return str(value).strip() if isinstance(value, (str, int, float)) else default


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def chatbot_shell(request, params: Dict[str, Any]) -> Dict[str, Any]:
    p = params or {}
    panel_params = dict(_as_dict(p.get("panel_params")))
    panel_params.setdefault("messages_alias", "chatbot/messages")
    panel_params.setdefault("messages_params", {})
    panel_params.setdefault("input_alias", "chatbot/input")
    panel_params.setdefault("input_params", {})
    panel_params.setdefault("footer", {})
    if p.get("session_id") and "session_id" not in panel_params:
        panel_params["session_id"] = _as_str(p.get("session_id"))

    messages_params = dict(_as_dict(panel_params.get("messages_params")))
    panel_params["messages_params"] = messages_params
    input_params = dict(_as_dict(panel_params.get("input_params")))
    panel_params["input_params"] = input_params

    segments = getattr(request, "_segments", None)
    consent = getattr(segments, "consent", "N") if segments else "N"
    if consent != "Y":
        consent_params = dict(_as_dict(p.get("consent_params")))
        panel_params["messages_alias"] = "chatbot/consent_gate"
        panel_params["messages_params"] = consent_params
        input_params["disabled"] = True
        input_params.setdefault("placeholder", "Activez l'assistant pour écrire.")
    else:
        panel_params["messages_alias"] = "chatbot/messages"
        panel_params["messages_params"] = messages_params
        input_params.pop("disabled", None)
    enabled_flag = bool(getattr(settings, "CHATBOT_ENABLED", True))
    enabled_param = _as_bool(p.get("enabled"), True)
    return {
        "enabled": enabled_flag and enabled_param,
        "trigger_label": _as_str(p.get("trigger_label"), "Assistant"),
        "trigger_aria": _as_str(p.get("trigger_aria"), "Ouvrir le chatbot"),
        "panel_title": _as_str(p.get("panel_title"), "Assistant Lumière"),
        "panel_description": _as_str(p.get("panel_description"), "Posez vos questions et recevez une réponse instantanée."),
        "panel_alias": _as_str(p.get("panel_alias"), "chatbot/panel"),
        "panel_params": panel_params,
    }


def chatbot_panel(request, params: Dict[str, Any]) -> Dict[str, Any]:
    p = params or {}
    header = _as_dict(p.get("header"))
    footer = _as_dict(p.get("footer"))
    return {
        "title": _as_str(header.get("title"), "Assistant Lumière"),
        "subtitle": _as_str(header.get("subtitle"), "Besoin d'aide ?"),
        "session_id": _as_str(p.get("session_id")),
        "messages_alias": _as_str(p.get("messages_alias"), "chatbot/messages"),
        "messages_params": _as_dict(p.get("messages_params")),
        "input_alias": _as_str(p.get("input_alias"), "chatbot/input"),
        "input_params": _as_dict(p.get("input_params")),
        "footer_links": [
            {
                "label": _as_str(item.get("label")),
                "href": _as_str(item.get("href"), "#"),
                "new_tab": _as_bool(item.get("new_tab"), True),
            }
            for item in _as_list(footer.get("links"))
            if _as_str(item.get("label"))
        ],
    }


def chatbot_messages(request, params: Dict[str, Any]) -> Dict[str, Any]:
    p = params or {}
    messages: List[Dict[str, str]] = []
    for item in _as_list(p.get("messages")):
        if not isinstance(item, dict):
            continue
        role = _as_str(item.get("role"), "assistant")
        messages.append(
            {
                "id": _as_str(item.get("id")),
                "role": role,
                "content_html": escape(_as_str(item.get("content"))).replace("\n", "<br />"),
            }
        )
    empty_state = _as_dict(p.get("empty_state"))
    return {
        "messages": messages,
        "empty_title": _as_str(empty_state.get("title"), "Je suis là pour vous aider."),
        "empty_body": _as_str(empty_state.get("body"), "Posez votre première question pour démarrer la conversation."),
    }


def chatbot_input(request, params: Dict[str, Any]) -> Dict[str, Any]:
    p = params or {}
    actions = []
    for action in _as_list(p.get("actions")):
        if not isinstance(action, dict):
            continue
        label = _as_str(action.get("label"))
        if not label:
            continue
        actions.append(
            {
                "label": label,
                "value": _as_str(action.get("value")),
            }
        )
    return {
        "placeholder": _as_str(p.get("placeholder"), "Écrire un message..."),
        "submit_label": _as_str(p.get("submit_label"), "Envoyer"),
        "disabled": _as_bool(p.get("disabled"), False),
        "actions": actions,
    }


def chatbot_consent_gate(request, params: Dict[str, Any]) -> Dict[str, Any]:
    p = params or {}
    return {
        "title": _as_str(p.get("title"), "Activer l'assistant"),
        "body": _as_str(
            p.get("body"),
            "Pour profiter de l'assistant, autorisez l'utilisation de cookies fonctionnels.",
        ),
        "cta_label": _as_str(p.get("cta_label"), "J'accepte"),
        "privacy_url": _as_str(p.get("privacy_url"), "/mentions-legales"),
    }
