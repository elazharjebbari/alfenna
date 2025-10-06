from __future__ import annotations
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, root_validator, ValidationError
import logging

log = logging.getLogger("forms.shell.contracts")


class BackendConfig(BaseModel):
    endpoint_url: Optional[str] = Field(default=None)
    require_signed_token: bool = False
    sign_url: Optional[str] = None

    class Config:
        extra = "forbid"


class WizardChildParams(BaseModel):
    """
    Paramètres autorisés à descendre vers le *child* forms/wizard_generic.
    On reste volontairement strict pour éviter toute injection arbitraire.
    """
    flow_key: Optional[str] = Field(default=None, description="Identifiant du flow")
    config_json: Optional[str] = Field(default=None, description="Payload JSON déjà sérialisé")
    backend_config: Optional[BackendConfig] = None
    ui_texts: Dict[str, str] = Field(default_factory=dict)

    class Config:
        extra = "forbid"


class WizardCtxDeprecated(BaseModel):
    """
    Ancien bloc (déprécié) encore accepté pour compatibilité.
    Il sera mappé vers `child` si ce dernier est absent.
    """
    flow_key: Optional[str] = None
    config_json: Optional[str] = None

    class Config:
        extra = "ignore"


class ShellContractV3(BaseModel):
    # Champs UX du parent (inchangés)
    flow_key: Optional[str] = None  # toléré si certains appels historiques s'en servent encore
    display: str = Field(default="inline", description="inline | modal")
    title_html: Optional[str] = None
    subtitle_html: Optional[str] = None
    cta_label: Optional[str] = None
    backend_config: Optional[BackendConfig] = None
    marketing_context: Dict[str, Any] = Field(default_factory=dict)
    ui_texts: Dict[str, str] = Field(default_factory=dict)

    # NOUVEAU : bloc enfant whitelisté
    child: Optional[WizardChildParams] = Field(
        default=None, description="Paramètres transmis au composant enfant forms/wizard_generic"
    )

    # DÉPRÉCIÉ : mappé automatiquement vers child si nécessaire
    wizard_ctx: Optional[WizardCtxDeprecated] = Field(
        default=None, description="DEPRECATED — utiliser `child`"
    )

    @root_validator(pre=True)
    def _map_deprecated_wizard_ctx(cls, values):
        # Si `child` est absent mais `wizard_ctx` présent, on mappe proprement
        child = values.get("child")
        wctx = values.get("wizard_ctx")
        if not child and wctx:
            log.warning("[forms.shell.contracts] `wizard_ctx` est déprécié. Utilisez `child`.")
            # On ne mappe que les champs autorisés
            values["child"] = {
                "flow_key": wctx.get("flow_key"),
                "config_json": wctx.get("config_json"),
            }
        return values

    class Config:
        extra = "forbid"
