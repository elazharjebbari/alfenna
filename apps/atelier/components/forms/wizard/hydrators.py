# apps/atelier/components/forms/wizard/hydrators.py.py
from __future__ import annotations
import json
import logging
from django.conf import settings
from django.urls import reverse, NoReverseMatch
from .contracts import validate_and_fingerprint

log = logging.getLogger("forms.wizard.hydrators.py")

def hydrate(request, params=None):
    """
    Construit un contexte minimal **validé** pour le child.
    Expose:
      - config_json (utilisé par le template HTML, inchangé → parité DOM)
      - flow_key (pour vary_on)
      - config_sha1 (pour vary_on)
    """
    params = dict(params or {})

    # Fallbacks pour compat si le parent oublie un champ :
    flow_key = params.get("flow_key") or getattr(settings, "FLOWFORMS_DEFAULT_FLOW_KEY", "ff")
    if not params.get("config_json"):
        # Construit un JSON par défaut (identique à l'existant)
        default_urlname = getattr(settings, "FLOWFORMS_ENDPOINT_COLLECT_URLNAME", "leads:collect")
        try:
            endpoint_url = reverse(default_urlname)
        except NoReverseMatch:
            endpoint_url = "/api/leads/collect/"

        require_signed = bool(getattr(settings, "FLOWFORMS_REQUIRE_SIGNED", False))
        sign_urlname = getattr(settings, "FLOWFORMS_SIGN_URLNAME", "leads:sign")
        try:
            sign_url = reverse(sign_urlname) if require_signed else ""
        except NoReverseMatch:
            sign_url = ""

        cfg = {
            "flow_key": flow_key,
            "form_kind": params.get("form_kind") or "email_ebook",
            "endpoint_url": endpoint_url,
            "require_signed": require_signed,
            "sign_url": sign_url,
            "context": params.get("context") or {},
        }
        params["config_json"] = json.dumps(cfg, ensure_ascii=False)

    # Toujours poser flow_key (peut être ajouté par fallback ci-dessus)
    params["flow_key"] = flow_key

    # Validation forte + empreinte
    try:
        v_flow_key, v_config_json, config_norm, config_sha1 = validate_and_fingerprint(params)
    except Exception as e:
        # Fail-fast clair : on remonte une ValueError explicite (capturable par les tests)
        log.error("wizard/hydrate: contrat invalide (%s)", e)
        raise

    # Contexte rendu (DOM **inchangé**: seul config_json est consommé par le template)
    return {
        "config_json": v_config_json,
        "flow_key": v_flow_key,
        "config_sha1": config_sha1,
        # Note: on n'expose pas config_norm pour éviter la fuite d'implémentation
    }