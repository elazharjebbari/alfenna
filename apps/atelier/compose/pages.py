# apps/atelier/compose/pages.py
from __future__ import annotations
from typing import Dict, List
from ..config.loader import get_page_spec as _get_page_spec

def page_meta(page_id: str, *, namespace: str | None = None) -> Dict:
    spec = _get_page_spec(page_id, namespace=namespace) or {}
    return spec.get("meta", {}) or {}

def get_slots(page_id: str, *, namespace: str | None = None) -> List[str]:
    spec = _get_page_spec(page_id, namespace=namespace) or {}
    slots = spec.get("slots", {}) or {}
    return list(slots.keys())

def page_spec(page_id: str, *, namespace: str | None = None) -> Dict:
    return _get_page_spec(page_id, namespace=namespace) or {}
