# apps/atelier/components/contracts.py
from __future__ import annotations
from typing import Any, Mapping, Sequence, Tuple, Dict, List, Optional
import re

from apps.atelier.components.registry import get as get_component
from typing import Optional

__all__ = ["ContractValidationError", "validate"]

LIST_RE = re.compile(r"^list\[(.+)\]$", re.IGNORECASE)


class ContractValidationError(Exception):
    """Erreur de validation de contrat composant."""
    pass


# ------------------------------
# Helpers de validation récursive
# ------------------------------

def _is_bool(v: Any) -> bool:
    return isinstance(v, bool)


def _is_int(v: Any) -> bool:
    # En Python bool hérite de int; on exclut les bool explicites.
    return isinstance(v, int) and not isinstance(v, bool)


def _is_float(v: Any) -> bool:
    return isinstance(v, float) or _is_int(v)


def _type_name_ok(v: Any, tname: str) -> bool:
    t = (tname or "").strip().lower()
    if t in ("any", "*", ""):
        return True
    if t in ("str", "string"):
        return isinstance(v, str)
    if t in ("int", "integer"):
        return _is_int(v)
    if t in ("float", "double", "number"):
        return _is_float(v)
    if t in ("bool", "boolean"):
        return _is_bool(v)
    if t in ("list", "array"):
        return isinstance(v, (list, tuple))
    if t in ("dict", "mapping", "object"):
        return isinstance(v, Mapping)

    # list[...] générique
    m = LIST_RE.match(t)
    if m:
        inner = m.group(1).strip()
        if not isinstance(v, (list, tuple)):
            return False
        for i, it in enumerate(v):
            if not _validate_value(it, inner, path=f"[{i}]", errors={}):
                return False
        return True

    # Type inconnu → traité comme descriptif (on accepte la valeur)
    return True


def _validate_list_with_inner_schema(v: Any, inner_schema: Any, path: str, errors: Dict[str, str]) -> None:
    if not isinstance(v, (list, tuple)):
        errors[path] = f"type invalide: attendu list[...]"
        return
    for idx, item in enumerate(v):
        _validate_value(item, inner_schema, f"{path}[{idx}]", errors)


def _validate_object_with_schema(v: Any, schema: Mapping[str, Any], path: str, errors: Dict[str, str]) -> None:
    if not isinstance(v, Mapping):
        errors[path] = "type invalide: attendu dict/object"
        return
    for raw_key, subspec in (schema or {}).items():
        key = str(raw_key)
        optional = key.endswith("?")
        field = key[:-1] if optional else key
        subpath = f"{path}.{field}" if path else field
        if field not in v:
            if not optional:
                errors[subpath] = "champ requis"
            continue
        _validate_value(v[field], subspec, subpath, errors)


def _validate_value(v: Any, type_spec: Any, path: str, errors: Dict[str, str]) -> bool:
    """
    Valide v selon type_spec. Ajoute dans errors[path] en cas d'erreur.
    Retourne True si OK, False sinon.
    type_spec peut être:
      - str: "str" | "int" | "list[str]" | "any" | ...
      - dict: schéma d'objet, ex {"label":"str","url?":"str"}
      - list (len==1): schéma d'items, ex [{"icon":"str","html":"str"}]
      - list (len!=1): traité comme 'list' générique (v doit être list/tuple)
      - None: accepté (any)
    """
    # None → on accepte (laisser les 'required' gérer l'absence/None)
    if type_spec is None:
        return True

    # Spécification par chaîne
    if isinstance(type_spec, str):
        if _type_name_ok(v, type_spec):
            # pour list[...] générique, _type_name_ok fait déjà la récursion
            return True
        errors[path] = f"type invalide: attendu {type_spec}"
        return False

    # Schéma d'objet
    if isinstance(type_spec, Mapping):
        _validate_object_with_schema(v, type_spec, path, errors)
        return path not in errors and not any(k.startswith(path + ".") for k in errors.keys())

    # Schéma de liste (items)
    if isinstance(type_spec, Sequence):
        ts = list(type_spec)
        if len(ts) == 1:
            _validate_list_with_inner_schema(v, ts[0], path, errors)
            return path not in errors and not any(k.startswith(path + "[") for k in errors.keys())
        # Liste non-schématique → au moins que v soit une liste
        if isinstance(v, (list, tuple)):
            return True
        errors[path] = "type invalide: attendu list"
        return False

    # Type de spec non reconnu → on considère 'any'
    return True


# ------------------------------
# API publique
# ------------------------------

def _collect_contract(alias: str, *, namespace: Optional[str] = None) -> Tuple[Mapping[str, Any], Mapping[str, Any]]:
    comp = get_component(alias, namespace=namespace)
    c = comp.get("contract") or {}
    required = c.get("required") or {}
    optional = c.get("optional") or {}
    if not isinstance(required, Mapping):
        required = {}
    if not isinstance(optional, Mapping):
        optional = {}
    return required, optional


def validate(alias: str, ctx: Mapping[str, Any], *, namespace: Optional[str] = None) -> None:
    """
    Valide le contexte ctx par rapport au contrat du composant.
    Lève ContractValidationError si erreurs.
    """
    required, optional = _collect_contract(alias, namespace=namespace)
    ctx = ctx or {}

    errors: Dict[str, str] = {}

    # Champs requis
    for field, spec in required.items():
        if field not in ctx or ctx.get(field) is None:
            errors[field] = "champ requis"
            continue
        _validate_value(ctx.get(field), spec, field, errors)

    # Champs optionnels (si présents)
    for field, spec in optional.items():
        if field in ctx and ctx.get(field) is not None:
            _validate_value(ctx.get(field), spec, field, errors)

    if errors:
        # Format compatible avec tes scripts d'audit (erreurs={...})
        raise ContractValidationError(f"[contracts] alias={alias} erreurs={errors}")
