"""
Façade de services robuste pour l'app Atelier.

- Normalisation des segments (dict plat et sûr).
- Génération de clé de cache canonique et stable.
- Façade de cache de fragments avec L1 request-local et télémétrie légère.
"""

from __future__ import annotations
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, List, Optional

from apps.atelier.compose.cache import (
    get_fragment as _backend_get,
    set_fragment as _backend_set,
    exists as _backend_exists,
)

# -------------------------
# Helpers "publics"
# -------------------------

def get_request_id(request) -> str:
    """Retourne l'ID de requête (défini par le middleware request_id)."""
    return getattr(request, "request_id", "") or ""


def _normalize_str(val: Any) -> str:
    if val is None:
        return ""
    try:
        s = str(val)
    except Exception:
        return ""
    # On retire les séparateurs "dangereux" pour la clé
    return s.strip().replace("|", "").replace("\n", " ").replace("\r", " ")


def _normalize_lang(lang: str) -> str:
    lang = (lang or "fr").strip().lower()
    # Normalise en code court
    return lang.split(",")[0].split("-")[0][:2] or "fr"


def _normalize_device(device: str) -> str:
    d = (device or "d").strip().lower()
    return "m" if d in ("m", "mobile") else "d"


def _normalize_consent(consent: str) -> str:
    c = (consent or "N").strip().upper()
    return "Y" if c == "Y" else "N"


def _segments_to_dict(segments_obj: Any) -> Dict[str, str]:
    """
    Accepte:
      - dataclass Segments du middleware
      - dict
      - None
    Retourne toujours un dict plat avec clés attendues.
    """
    if segments_obj is None:
        data = {}
    elif is_dataclass(segments_obj):
        data = asdict(segments_obj)
    elif isinstance(segments_obj, dict):
        data = dict(segments_obj)
    else:
        data = {}

    return {
        "lang": _normalize_lang(data.get("lang", "fr")),
        "device": _normalize_device(data.get("device", "d")),
        "consent": _normalize_consent(data.get("consent", "N")),
        "source": _normalize_str(data.get("source", "")),
        "campaign": _normalize_str(data.get("campaign", "")),
        # qa est booléen mais on le traite séparément dans build_cache_key
    }


def get_segments(request) -> Dict[str, str]:
    """
    Retourne un dict de segments normalisés depuis request._segments (dataclass ou dict).
    Ne lève jamais d'exception.
    """
    try:
        seg_obj = getattr(request, "_segments", None)
        return _segments_to_dict(seg_obj)
    except Exception:
        return {
            "lang": "fr",
            "device": "d",
            "consent": "N",
            "source": "",
            "campaign": "",
        }


def build_cache_key(
    page_id: str,
    slot_id: str,
    variant_key: str,
    segments: Dict[str, str] | Any,
    content_rev: str,
    qa: bool = False,
    *,
    site_version: str = "core",
) -> str:
    """
    Construit la clé canonique (ordre contractuel) :
      route|slot|variant|lang|device|consent|source|campaign|content_rev|v:<slug>[|qa]
    """
    seg = _segments_to_dict(segments)
    parts = [
        _normalize_str(page_id),
        _normalize_str(slot_id),
        _normalize_str(variant_key or "A"),
        seg["lang"],
        seg["device"],
        seg["consent"],
        seg["source"],
        seg["campaign"],
        _normalize_str(content_rev or "v1"),
        f"v:{_normalize_str(site_version or 'core')}",
    ]
    if qa:
        parts.append("qa")
    return "|".join(parts)


def collect_assets(component_aliases: List[str]) -> Dict[str, List[str]]:
    """Placeholder (conservé pour compatibilité ascendante)."""
    return {"css": [], "js": [], "head": []}


# -------------------------
# Façade de cache fragments (A-2)
# -------------------------

class FragmentCache:
    """
    Façade de cache avec L1 "request-local" et télémétrie légère.

    - L1: évite de recharger/hydrater/rendre 2x le même fragment dans une requête.
    - Stats: request._atelier_cache_stats = {"l1_hits": int, "backend_hits": int, "backend_sets": int}
    """

    def __init__(self, request: Optional[Any] = None) -> None:
        self.request = request
        if request is not None:
            if not hasattr(request, "_atelier_fragments_l1"):
                request._atelier_fragments_l1 = {}
            if not hasattr(request, "_atelier_cache_stats"):
                request._atelier_cache_stats = {"l1_hits": 0, "backend_hits": 0, "backend_sets": 0}

    # --- internals ---

    def _l1(self) -> Dict[str, str]:
        if self.request is None:
            return {}
        return getattr(self.request, "_atelier_fragments_l1", {})

    def _stats(self) -> Dict[str, int]:
        if self.request is None:
            return {"l1_hits": 0, "backend_hits": 0, "backend_sets": 0}
        return getattr(self.request, "_atelier_cache_stats", {"l1_hits": 0, "backend_hits": 0, "backend_sets": 0})

    # --- API ---

    def get(self, key: str) -> Optional[str]:
        if not key:
            return None
        # L1
        l1 = self._l1()
        if key in l1:
            self._stats()["l1_hits"] += 1
            return l1.get(key)
        # Backend
        val = _backend_get(key)
        if val is not None and self.request is not None:
            l1[key] = val
        if val is not None:
            self._stats()["backend_hits"] += 1
        return val

    def set(self, key: str, html: Optional[str], ttl_seconds: Optional[int] = None) -> None:
        if not key or html is None:
            return
        _backend_set(key, html, ttl_seconds)
        if self.request is not None:
            self._l1()[key] = html
        self._stats()["backend_sets"] += 1

    def exists(self, key: str) -> bool:
        if not key:
            return False
        if key in self._l1():
            return True
        return _backend_exists(key)

    def stats(self) -> Dict[str, int]:
        return dict(self._stats())


def get_cache_stats(request) -> Dict[str, int]:
    """Expose les statistiques L1/backend pour debug/tests."""
    return getattr(request, "_atelier_cache_stats", {"l1_hits": 0, "backend_hits": 0, "backend_sets": 0})
