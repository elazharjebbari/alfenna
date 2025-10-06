"""
Validation de configuration (manifests & pages).
Soft en runtime (logs/checks), stricte en CI si activé.
"""
from __future__ import annotations
from typing import Any, Dict, List, Tuple


KNOWN_TYPES = {"str", "bool", "int", "float", "list", "dict", "url"}


def _is_list_str(x: Any) -> bool:
    return isinstance(x, list) and all(isinstance(i, str) for i in x)


def validate_manifest_data(data: Dict[str, Any], *, source: str = "") -> List[str]:
    """
    Retourne une liste de warnings (erreurs bloquantes à la charge de l'appelant).
    """
    warns: List[str] = []
    alias = (data.get("alias") or "").strip()
    if not alias:
        raise ValueError(f"[schema.manifest] alias manquant ({source})")
    template = (data.get("template") or "").strip()
    if not template:
        # autorisé si component.html adjacent, l'appelant vérifiera
        warns.append(f"[schema.manifest] template absent (ok si 'component.html' adjacent) — {alias}")

    assets = data.get("assets") or {}
    for k in ("head", "css", "js", "vendors"):
        if not isinstance(assets.get(k, []), list):
            warns.append(f"[schema.manifest] assets.{k} doit être une liste — {alias}")

    contract = data.get("contract") or {}
    for sec in ("required", "optional"):
        sect = contract.get(sec) or {}
        if not isinstance(sect, dict):
            warns.append(f"[schema.manifest] contract.{sec} doit être un dict — {alias}")
        else:
            for field, tname in sect.items():
                if isinstance(tname, str) and tname not in KNOWN_TYPES:
                    warns.append(f"[schema.manifest] contract type inconnu '{tname}' pour '{field}' — {alias}")

    hydrate = data.get("hydrate") or {}
    if hydrate:
        if not isinstance(hydrate, dict):
            warns.append(f"[schema.manifest] hydrate doit être un dict — {alias}")
        else:
            if "calls" in hydrate and not isinstance(hydrate["calls"], list):
                warns.append(f"[schema.manifest] hydrate.calls doit être une liste — {alias}")
            if "params" in hydrate and not isinstance(hydrate["params"], dict):
                warns.append(f"[schema.manifest] hydrate.params doit être un dict — {alias}")

    render = data.get("render") or {}
    if render and not isinstance(render, dict):
        warns.append(f"[schema.manifest] render doit être un dict — {alias}")
    else:
        if "cacheable" in render and not isinstance(render["cacheable"], (bool, type(None))):
            warns.append(f"[schema.manifest] render.cacheable doit être bool|None — {alias}")
        if "vary_on" in render and not _is_list_str(render["vary_on"]):
            warns.append(f"[schema.manifest] render.vary_on doit être une liste de str — {alias}")

    return warns


def validate_pages_config(conf: Dict[str, Any]) -> List[str]:
    """
    Valide les slots/pages normalisés.
    """
    warns: List[str] = []
    pages = conf.get("pages") or {}
    if not isinstance(pages, dict):
        raise ValueError("[schema.pages] 'pages' doit être un dict")

    for pid, pspec in pages.items():
        if not isinstance(pspec, dict):
            warns.append(f"[schema.pages] page '{pid}' doit être un dict")
            continue
        slots = pspec.get("slots") or {}
        if not isinstance(slots, dict):
            warns.append(f"[schema.pages] page '{pid}': 'slots' doit être un dict")
            continue
        for sid, sdef in slots.items():
            if not isinstance(sdef, dict):
                warns.append(f"[schema.pages] slot '{pid}.{sid}' doit être un dict")
                continue
            variants = sdef.get("variants") or {}
            if not isinstance(variants, dict):
                warns.append(f"[schema.pages] slot '{pid}.{sid}': 'variants' doit être un dict")
            params = sdef.get("params")
            if params is not None and not isinstance(params, dict):
                warns.append(f"[schema.pages] slot '{pid}.{sid}': 'params' doit être un dict")
    return warns
