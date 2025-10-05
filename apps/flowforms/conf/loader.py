# apps/flowforms/conf/loader.py
from __future__ import annotations

import os
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import yaml
from django.conf import settings
from django.core.exceptions import ValidationError

from ..conf.schema import FlowFormsConfig  # ton schéma Pydantic/attrs

# -------------------------
# Helpers
# -------------------------

def _policy_path() -> str:
    path = getattr(settings, "FLOWFORMS_POLICY_YAML", "")
    if not path:
        raise FileNotFoundError("FLOWFORMS_POLICY_YAML n’est pas défini dans settings.")
    return str(path)

def _file_mtime_sig(path: str) -> float:
    try:
        st = os.stat(path)
        # On arrondit pour stabilité (certaines FS ont une faible résolution)
        return round(st.st_mtime, 3)
    except FileNotFoundError:
        # Permet de remonter une erreur propre plus tard
        return -1.0

def _read_yaml(path: str) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Fichier de configuration introuvable: {path}")
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data

# -------------------------
# Cache interne
# -------------------------

@lru_cache(maxsize=1)
def _load_config_cached(path: str, mtime_sig: float) -> FlowFormsConfig:
    """
    NE PAS appeler directement : passez par load_config().
    La clé de cache inclut (path, mtime_sig) => reload implicite si le fichier a changé.
    """
    if mtime_sig < 0:
        raise FileNotFoundError(f"Fichier de configuration introuvable: {path}")

    raw = _read_yaml(path)

    # Validation schéma stricte (lance ValidationError si invalide)
    try:
        cfg = FlowFormsConfig.model_validate(raw)  # Pydantic v2
    except Exception as e:
        # Uniformise l’exception vers Django
        raise ValidationError(str(e)) from e

    return cfg

def invalidate_config_cache() -> None:
    """Vide explicitement le cache LRU — à utiliser dans les tests et le linter si besoin."""
    _load_config_cached.cache_clear()

# -------------------------
# API publique
# -------------------------

def load_config(*, reload: bool = False) -> FlowFormsConfig:
    """
    Charge la config flowforms, avec cache.
    - reload=True => invalide le cache et recharge (utile dans tests/commandes).
    - sinon : cache (clé = (path, mtime)).
    """
    path = _policy_path()
    mtime_sig = _file_mtime_sig(path)

    if reload:
        invalidate_config_cache()

    return _load_config_cached(path, mtime_sig)

# apps/flowforms/conf/loader.py (remplace entièrement get_flow)

def get_flow(flow_key: str, *, reload: bool = False) -> Dict[str, Any]:
    """
    Récupère un flow par clé à partir de la config chargée.
    Compatible avec:
      - Pydantic v2: cfg.flows = List[FlowConfig]
      - objets dict-like (fallback)
    Retourne toujours un dict Python.
    """
    cfg = load_config(reload=reload)
    flows = getattr(cfg, "flows", []) or []

    flow_obj = None
    if isinstance(flows, dict):
        # compat très ancienne forme
        flow_obj = flows.get(flow_key)
    else:
        # forme actuelle: liste de FlowConfig
        for f in flows:
            key = getattr(f, "key", None) or (f.get("key") if isinstance(f, dict) else None)
            if key == flow_key:
                flow_obj = f
                break

    if not flow_obj:
        raise KeyError(f"Flow '{flow_key}' introuvable dans {getattr(settings, 'FLOWFORMS_POLICY_YAML', '<settings>')}.")

    try:
        # Pydantic v2
        return flow_obj.model_dump()
    except AttributeError:
        return dict(flow_obj)