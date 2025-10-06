import json, uuid, hashlib
from django.urls import reverse
from django.utils.timezone import now

def _mk_flow_key(base="ff"):
    return f"{base}-{uuid.uuid4().hex[:8]}"

def _mk_backend_config(request, params):
    """
    Construit la config consommée par le runtime front.
    En dev on peut désactiver la signature pour tester (cf. policy).
    """
    endpoint_url = reverse("leads:collect")  # /api/leads/collect/
    # Flags runtime (le back fait foi via policy; ici c'est indicatif pour le front)
    cfg = {
        "endpoint_url": endpoint_url,
        "form_kind": params.get("form_kind") or "email_ebook",
        "require_idempotency": True,
        # En prod: True + fournir sign_url (endpoint de signature même origine)
        "require_signed_token": bool(params.get("require_signed_token", False)),
        "sign_url": params.get("sign_url") or None,
        "client_ts_skew_s": 7200,
    }
    return cfg

def forms_shell(request, params):
    """
    Parent: prépare flow_key, backend_config, marketing_context, et pousse au child.
    """
    flow_key = params.get("flow_key") or _mk_flow_key("ffinline")
    backend_config = params.get("backend_config") or {}
    backend_config = _mk_backend_config(request, backend_config)

    # Contexte marketing (simple)
    q = request.GET
    marketing_context = {
        "campaign": q.get("campaign", ""),
        "source":   q.get("source", ""),
        "utm_source":   q.get("utm_source", ""),
        "utm_medium":   q.get("utm_medium", ""),
        "utm_campaign": q.get("utm_campaign", ""),
    }

    # Textes UI par défaut (surclassables)
    ui_texts = {
        "next": "Suivant",
        "prev": "Précédent",
        "submit": "Terminer",
        "thanks_title": "Merci !",
        "thanks_text": "Votre demande a bien été prise en compte.",
        "error_generic": "Une erreur est survenue. Merci de réessayer.",
        "error_rate_limit": "Trop de tentatives. Réessayez plus tard.",
    }
    ui_texts.update(params.get("ui_texts") or {})

    # Surcharge de titres/sous-titres éventuels conservée
    shell = {
        "flow_key": flow_key,
        "display": params.get("display") or "inline",
        "cta_label": params.get("cta_label") or "Je m'inscris",
        "title_html": params.get("title_html") or "Accédez à la formation",
        "subtitle_html": params.get("subtitle_html") or "Entrez votre email pour démarrer.",
        "backend_config": backend_config,
        "marketing_context": marketing_context,
        "ui_texts": ui_texts,
    }

    child_params = params.get("child") or {}
    schema_payload = child_params.get("schema") or {
        "steps": [
            {"idx": 1, "fields": [{"name": "email", "required": True, "validators": ["email"]}]},
            {"idx": 2, "fields": [{"name": "first_name", "required": False}]},
            {"idx": 3, "thank_you": True},
        ]
    }

    # Paramètres transmis au child (wizard)
    shell["children"] = {
        "wizard": {
            "flow_key": flow_key,
            "backend_config": backend_config,
            "ui_texts": ui_texts,
            "schema": schema_payload,
        }
    }
    shell["schema"] = schema_payload
    return shell

def wizard_generic(request, params):
    """
    Enfant: construit le JSON consommé par le runtime, en combinant schema/backend_config/ui_texts.
    """
    flow_key = params["flow_key"]
    cfg = params.get("backend_config") or {}
    ui = params.get("ui_texts") or {}
    schema = params.get("schema") or {}

    config_payload = {
        "flow_key": flow_key,
        "form_kind": cfg.get("form_kind", "email_ebook"),
        "endpoint_url": cfg.get("endpoint_url"),
        "require_idempotency": bool(cfg.get("require_idempotency", True)),
        "require_signed_token": bool(cfg.get("require_signed_token", False)),
        "sign_url": cfg.get("sign_url"),
        "client_ts_skew_s": int(cfg.get("client_ts_skew_s", 7200)),
        "ui": ui,
        "schema": schema,
        # Context marketing (facultatif; fusionné côté runtime)
        "context": {
            "client_ts": now().isoformat(),
            "locale": getattr(request, "LANGUAGE_CODE", "fr"),
        },
    }

    cfg_str = json.dumps(config_payload, ensure_ascii=False)
    config_sha1 = hashlib.sha1(cfg_str.encode("utf-8")).hexdigest()

    return {
        "flow_key": flow_key,
        "backend_config": cfg,
        "ui_texts": ui,
        "schema": schema,
        "config_json": cfg_str,
        "config_sha1": config_sha1,
    }
