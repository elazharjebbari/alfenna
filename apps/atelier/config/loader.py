# apps/atelier/config/loader.py
from __future__ import annotations
from functools import lru_cache
from pathlib import Path
from typing import Dict, Any, List
import yaml

from django.conf import settings

BASE_DIR = Path(settings.BASE_DIR)
CFG_ROOT = BASE_DIR / "configs" / "atelier"
FALLBACK_NAMESPACE = "core"
RESERVED_NAMESPACE_DIRS = {"base", "__pycache__"}
_REQUIRED_VARY_FIELDS = ("lang", "site_version")

# --------- Normalisation interne (slots/variants/children) ---------

def _normalize_slots(page_spec: dict) -> dict:
    """
    Accepte:
      - dict: {"slots": {"hero": {...}, "header": {...}}}
      - list: {"slots": [{"id":"hero", ...}, {"id":"header", ...}]}
    Retourne toujours un dict {"slots": {slot_id: slot_spec}}
    """
    slots = page_spec.get("slots")
    if not slots:
        page_spec["slots"] = {}
        return page_spec

    if isinstance(slots, dict):
        page_spec["slots"] = slots
        return page_spec

    if isinstance(slots, list):
        d: Dict[str, dict] = {}
        for i, s in enumerate(slots):
            if not isinstance(s, dict):
                raise ValueError(f"Slot à l'index {i} n'est pas un dict (type={type(s)}).")
            sid = (s or {}).get("id")
            if not sid:
                raise ValueError(f"Slot à l'index {i} sans champ 'id'.")
            if sid in d:
                raise ValueError(f"Slot en double: '{sid}'.")
            s = dict(s)
            s.pop("id", None)
            d[sid] = s
        page_spec["slots"] = d
        return page_spec

    raise ValueError(f"Type inattendu pour 'slots': {type(slots)} (attendu dict ou list).")


def _normalize_variants(slot_spec: dict) -> dict:
    """
    Pour chaque slot, accepte:
      - dict: {"variants": {"A": "hero/cover", "B": "hero/slider"}}
      - list: {"variants": [{"key":"A","component":"hero/cover"}, {"key":"B","component":"hero/slider"}]}
    Retourne toujours {"variants": {key: component_alias}}
    Si le slot a 'component' (non A/B), on le convertit en variants {"A": component}
    """
    if "component" in slot_spec and not slot_spec.get("variants"):
        comp = slot_spec.get("component")
        if comp:
            slot_spec["variants"] = {"A": comp}
            slot_spec.pop("component", None)

    variants = slot_spec.get("variants")
    if not variants:
        slot_spec["variants"] = {}
        return slot_spec

    if isinstance(variants, dict):
        slot_spec["variants"] = variants
        return slot_spec

    if isinstance(variants, list):
        d: Dict[str, str] = {}
        for i, v in enumerate(variants):
            if not isinstance(v, dict):
                raise ValueError(f"Variant à l'index {i} n'est pas un dict (type={type(v)}).")
            key = (v or {}).get("key")
            comp = (v or {}).get("component")
            if not key:
                raise ValueError(f"Variant à l'index {i} sans 'key'.")
            if not comp:
                raise ValueError(f"Variant '{key}' sans 'component'.")
            if key in d:
                raise ValueError(f"Variant en double: '{key}'.")
            d[key] = comp
        slot_spec["variants"] = d
        return slot_spec

    raise ValueError(f"Type inattendu pour 'variants': {type(variants)} (attendu dict ou list).")


def _normalize_child_variants(spec: Any, *, where: str) -> Dict[str, str]:
    """
    Normalise le champ 'variants' d'un **child** dans pages.yml (override).
    Accepte alias direct (str), dict avec component/variants, ou list variants (key/component).
    """
    if isinstance(spec, str):
        return {"A": spec}
    if not isinstance(spec, dict):
        raise ValueError(f"{where}: type inattendu ({type(spec)}).")

    if "component" in spec and not spec.get("variants"):
        comp = spec.get("component")
        if not comp:
            raise ValueError(f"{where}: 'component' manquant.")
        return {"A": comp}

    variants = spec.get("variants")
    if not variants:
        return {}

    if isinstance(variants, dict):
        return {str(k): str(v) for k, v in variants.items()}

    if isinstance(variants, list):
        out: Dict[str, str] = {}
        for i, v in enumerate(variants):
            if not isinstance(v, dict):
                raise ValueError(f"{where}.variants[{i}]: non-dict.")
            key = (v.get("key") or "").strip()
            comp = (v.get("component") or "").strip()
            if not key or not comp:
                raise ValueError(f"{where}.variants[{i}]: key/component manquants.")
            if key in out:
                raise ValueError(f"{where}: variant en double '{key}'.")
            out[key] = comp
        return out

    raise ValueError(f"{where}.variants: type inattendu ({type(variants)}).")


def _normalize_children(slot_spec: dict, *, pid: str, sid: str) -> dict:
    """
    pages.yml — override facultatif des enfants du slot parent:
      children:
        menu: "nav/menu_alt"              # alias direct
        topbar:
          component: "header/topbar"
          params: { text_html: "<b>Promo</b>" }
          cache: true
        auth:
          variants: {"A": "header/auth"}
          cache: false
    Sortie normalisée:
      children: {
        child_id: {
          "variants": {...},   # dict
          "params": {...},     # dict
          "cache": bool|None,  # None => hérite du défaut
        }
      }
    """
    children = slot_spec.get("children")
    if not children:
        slot_spec["children"] = {}
        return slot_spec

    if not isinstance(children, dict):
        raise ValueError(f"Slot '{pid}.{sid}'.children doit être un dict.")

    out: Dict[str, dict] = {}
    for cid, cspec in children.items():
        cid = str(cid)
        where = f"pages.{pid}.slots.{sid}.children.{cid}"

        # variants (= alias effectif) — accepte alias direct
        variants = _normalize_child_variants(cspec, where=where)

        # params
        params = {}
        if isinstance(cspec, dict) and isinstance(cspec.get("params"), dict):
            params = dict(cspec["params"])

        # cache override
        cache = None
        if isinstance(cspec, dict) and "cache" in cspec:
            cache = bool(cspec["cache"])

        out[cid] = {"variants": variants, "params": params, "cache": cache}

    slot_spec["children"] = out
    return slot_spec


def _normalize_pages(conf: dict) -> dict:
    pages = conf.get("pages") or {}
    if not isinstance(pages, dict):
        raise ValueError(f"La section 'pages' doit être un dict (reçu {type(pages)}).")

    out: Dict[str, dict] = {}
    for pid, p in pages.items():
        if not isinstance(p, dict):
            raise ValueError(f"Page '{pid}' n'est pas un dict (type={type(p)}).")
        p = dict(p)  # copie défensive
        p = _normalize_slots(p)
        # Normaliser variants + children pour chaque slot
        slots = p.get("slots", {})
        for sid, spec in list(slots.items()):
            if not isinstance(spec, dict):
                raise ValueError(f"Slot '{pid}.{sid}' n'est pas un dict (type={type(spec)}).")
            spec = dict(spec)
            spec = _normalize_variants(spec)
            spec = _normalize_children(spec, pid=pid, sid=sid)
            slots[sid] = spec
        p["slots"] = slots
        out[pid] = p

    conf["pages"] = out
    return conf


def _normalize_experiments(conf: dict) -> dict:
    exps = conf.get("experiments") or {}
    if not isinstance(exps, dict):
        raise ValueError(f"La section 'experiments' doit être un dict (reçu {type(exps)}).")
    conf["experiments"] = exps
    return conf


def _normalize_cache(conf: dict) -> dict:
    cache = conf.get("cache") or {}
    if not isinstance(cache, dict):
        raise ValueError(f"La section 'cache' doit être un dict (reçu {type(cache)}).")
    cache.setdefault("defaults", {})
    cache.setdefault("slots", {})
    cache.setdefault("vary_fields", [])
    conf["cache"] = cache
    return conf


def _normalize_qa(conf: dict) -> dict:
    qa = conf.get("qa") or {}
    if not isinstance(qa, dict):
        raise ValueError(f"La section 'qa' doit être un dict (reçu {type(qa)}).")
    conf["qa"] = qa
    return conf


def _normalize_config(conf: dict) -> dict:
    conf = _normalize_pages(conf)
    conf = _normalize_experiments(conf)
    conf = _normalize_cache(conf)
    conf = _normalize_qa(conf)
    return conf


# --------- Chargement + cache ---------

def _config_dir(namespace: str) -> Path:
    return CFG_ROOT / namespace


def _resolve_namespace(namespace: str | None) -> str:
    slug = (namespace or "").strip() or FALLBACK_NAMESPACE
    root = _config_dir(slug)
    if root.exists():
        return slug
    return FALLBACK_NAMESPACE


def _read_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _config_payload(namespace: str) -> Dict[str, Any]:
    root = _config_dir(namespace)
    cfg: Dict[str, Any] = {"pages": {}, "experiments": {}, "cache": {}, "qa": {}}

    pages_raw = _read_yaml(root / "pages.yml")
    if isinstance(pages_raw, dict):
        cfg.update(pages_raw)

    experiments_raw = _read_yaml(root / "experiments.yml")
    if isinstance(experiments_raw, dict):
        cfg["experiments"] = (
            (experiments_raw.get("experiments") or experiments_raw)
            if "experiments" in experiments_raw else experiments_raw
        )

    cache_raw = _read_yaml(root / "cache.yml")
    if isinstance(cache_raw, dict):
        cfg["cache"] = (cache_raw.get("cache") or cache_raw) if "cache" in cache_raw else cache_raw

    qa_raw = _read_yaml(root / "qa.yml")
    if isinstance(qa_raw, dict):
        cfg["qa"] = (qa_raw.get("qa") or qa_raw) if "qa" in qa_raw else qa_raw

    return _normalize_config(cfg)


def _namespace_sentinel(namespace: str) -> float:
    root = _config_dir(namespace)
    mtimes = []
    for name in ("pages.yml", "experiments.yml", "cache.yml", "qa.yml"):
        path = root / name
        if path.exists():
            try:
                mtimes.append(path.stat().st_mtime)
            except OSError:
                continue
    return max(mtimes) if mtimes else 0.0


@lru_cache(maxsize=8)
def _load_configs_cached(namespace: str, sentinel: float) -> Dict[str, Any]:
    # sentinel n'est pas utilisé directement, mais force l'invalidation LRU quand les fichiers changent.
    return _config_payload(namespace)


def load_config(namespace: str | None = None) -> Dict[str, Any]:
    slug = _resolve_namespace(namespace)
    sentinel = _namespace_sentinel(slug)
    return _load_configs_cached(slug, sentinel)


# --------- Helpers lecture ---------

def clear_config_cache() -> None:
    """Force le rechargement (utile en scripts)."""
    _load_configs_cached.cache_clear()


def get_page_spec(page_id: str, *, namespace: str | None = None) -> Dict:
    return (load_config(namespace).get("pages", {}) or {}).get(page_id, {})


def _deep_merge_dicts(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(a or {})
    for key, value in (b or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge_dicts(result[key], value)
        else:
            result[key] = value
    return result


def _experiments_for(namespace: str | None) -> Dict[str, Any]:
    return load_config(namespace).get("experiments", {}) or {}


def _site_version_from_request(request) -> str:
    if request is None:
        return FALLBACK_NAMESPACE
    return getattr(request, "site_version", FALLBACK_NAMESPACE) or FALLBACK_NAMESPACE


def get_experiments_spec(*, namespace: str | None = None, request=None) -> Dict:
    if request is not None:
        site_version = _site_version_from_request(request)
        base = _experiments_for(FALLBACK_NAMESPACE)
        if site_version == FALLBACK_NAMESPACE:
            return base
        override = _experiments_for(site_version)
        return _deep_merge_dicts(base, override)
    return _experiments_for(namespace)


def get_cache_defaults(*, namespace: str | None = None) -> Dict:
    return load_config(namespace).get("cache", {}).get("defaults", {})


def get_cache_slots(*, namespace: str | None = None) -> Dict:
    return load_config(namespace).get("cache", {}).get("slots", {})


def get_vary_fields(*, namespace: str | None = None) -> list[str]:
    fields = list(load_config(namespace).get("cache", {}).get("vary_fields", []) or [])
    for required in _REQUIRED_VARY_FIELDS:
        if required not in fields:
            fields.append(required)
    return fields


def get_qa_policy(*, namespace: str | None = None) -> Dict:
    return load_config(namespace).get("qa", {})


@lru_cache(maxsize=1)
def list_namespaces() -> List[str]:
    names: List[str] = []
    if CFG_ROOT.exists():
        for entry in CFG_ROOT.iterdir():
            if not entry.is_dir():
                continue
            slug = entry.name.strip()
            if not slug or slug in RESERVED_NAMESPACE_DIRS:
                continue
            names.append(slug)
    if FALLBACK_NAMESPACE not in names:
        names.append(FALLBACK_NAMESPACE)
    # Preserve order of discovery while removing duplicates
    seen = set()
    ordered: List[str] = []
    for slug in names:
        if slug not in seen:
            seen.add(slug)
            ordered.append(slug)
    return ordered


def is_valid_namespace(namespace: str) -> bool:
    return (namespace or "").strip() in list_namespaces()
