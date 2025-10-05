# apps/atelier/components/forms/wizard/contracts.py
from __future__ import annotations
import json
import hashlib
from typing import Any, Dict, Tuple
from pydantic import BaseModel, Field, validator, ValidationError

class WizardContractV1(BaseModel):
    """
    Contrat d'entrée du child forms/wizard_generic (validation runtime fail-fast).
    """
    flow_key: str = Field(..., description="Identifiant de flow non vide")
    config_json: str = Field(..., description="Payload JSON sérialisé (parseable)")

    @validator("flow_key")
    def _flow_key_non_empty(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("flow_key vide")
        return v

    @validator("config_json")
    def _config_json_parseable(cls, v: str) -> str:
        raw = (v or "").strip()
        try:
            json.loads(raw)
        except Exception as e:
            raise ValueError(f"config_json invalide: {e}")
        return raw

    # -------- Helpers de normalisation / clé de variation --------

    @staticmethod
    def normalize_config(raw_json: str) -> Dict[str, Any]:
        """
        Normalise sémantiquement la config pour calculer un hash stable :
        - parse JSON
        - retire le bruit: clés None
        - IMPORTANT: on ignore 'flow_key' dans le hash (il varie déjà à part)
        - tri par clés (déterministe)
        """
        data = json.loads(raw_json)
        if isinstance(data, dict):
            data = {k: v for k, v in data.items() if v is not None}
            # flow_key déjà présent dans vary_on → on l'exclut du hash
            if "flow_key" in data:
                data = {k: v for k, v in data.items() if k != "flow_key"}
        return data

    @staticmethod
    def compute_config_sha1(config_norm: Dict[str, Any]) -> str:
        payload = json.dumps(config_norm, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def validate_and_fingerprint(params: Dict[str, Any]) -> Tuple[str, str, Dict[str, Any], str]:
    """
    Valide (fail-fast) et renvoie:
      - flow_key
      - config_json (tel que fourni)
      - config_norm (dict)
      - config_sha1 (12 chars)
    """
    model = WizardContractV1(**{
        "flow_key": params.get("flow_key"),
        "config_json": params.get("config_json"),
    })
    cfg_norm = WizardContractV1.normalize_config(model.config_json)
    cfg_sha1 = WizardContractV1.compute_config_sha1(cfg_norm)
    return model.flow_key, model.config_json, cfg_norm, cfg_sha1