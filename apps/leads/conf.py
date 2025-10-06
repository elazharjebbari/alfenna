import os, yaml
from django.conf import settings
from functools import lru_cache

def _load_yaml_policy(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}

@lru_cache(maxsize=1)
def load_policy() -> dict:
    # 1) settings dict
    settings_policy = getattr(settings, "LEADS_FIELD_POLICY", {})
    # 2) YAML
    yaml_policy = _load_yaml_policy(getattr(settings, "LEADS_POLICY_YAML", ""))
    # 3) DB (optionnel : pas implémenté ici pour rester simple)
    # Fusion simple : settings < YAML
    policy = {}
    policy.update(settings_policy or {})
    for k, v in (yaml_policy or {}).items():
        if isinstance(v, dict):
            policy.setdefault(k, {}).update(v)
        else:
            policy[k] = v
    return policy

def get_form_policy(form_kind: str, campaign: str | None = None) -> dict:
    p = load_policy()
    fk = (p.get("form_kinds") or {}).get(form_kind, {})
    # campaign overrides (non destructif)
    cov = (p.get("campaign_overrides") or {}).get(campaign or "", {})
    merged = dict(fk)
    if cov:
        merged_fields = dict(fk.get("fields", {}))
        merged_fields.update(cov.get("fields", {}))
        merged["fields"] = merged_fields
    return merged

def get_global_policy() -> dict:
    p = load_policy()
    return p.get("global") or {}