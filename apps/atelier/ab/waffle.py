# apps/atelier/ab/waffle.py
from __future__ import annotations

import hashlib
from typing import Dict, Optional, Tuple, Union

from django.http import HttpRequest

from apps.atelier.config.loader import get_experiments_spec
from apps.atelier.config.registry import get_qa_policy


def _stable_bucket(request: Optional[HttpRequest]) -> int:
    """Stable bucket in [0, 99] based on user id, ll_ab cookie or IP."""

    if request is None:
        return 0

    user = getattr(request, "user", None)
    user_pk = getattr(user, "pk", None)
    cookie_seed = request.COOKIES.get("ll_ab") if hasattr(request, "COOKIES") else None
    remote_addr = request.META.get("REMOTE_ADDR", "") if hasattr(request, "META") else ""

    seed = user_pk or cookie_seed or remote_addr or ""
    digest = hashlib.sha1(str(seed).encode("utf-8")).hexdigest()
    return int(digest[:4], 16) % 100


def _normalize_mapping(raw: Dict[str, str] | None) -> Dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items() if str(v)}


def resolve_variant(
    experiment_id: str,
    variants_or_request: Union[Dict[str, str], HttpRequest, None] = None,
    request: Optional[HttpRequest] = None,
) -> Tuple[str, str]:
    """Resolve which variant (A/B/...) should be rendered for an experiment."""

    resolved_request = request
    variants: Optional[Dict[str, str]] = None

    if resolved_request is None and isinstance(variants_or_request, HttpRequest):
        resolved_request = variants_or_request
    elif isinstance(variants_or_request, dict):
        variants = variants_or_request

    spec = get_experiments_spec(request=resolved_request) or {}
    exp = spec.get(experiment_id) or {}

    mapping = _normalize_mapping(variants or exp.get("variants"))
    if not mapping:
        return ("A", "")

    rollout_raw = exp.get("rollout", 0)
    try:
        rollout = int(rollout_raw or 0)
    except (TypeError, ValueError):
        rollout = 0

    bucket = _stable_bucket(resolved_request)

    if "B" in mapping and rollout > 0 and bucket < rollout:
        return ("B", mapping.get("B") or next(iter(mapping.values())))

    if "A" in mapping:
        return ("A", mapping["A"])

    key, alias = next(iter(mapping.items()))
    return (key, alias)

def is_preview_active(request, experiment_id: str) -> bool:
    """
    Mode preview QA activé si query param ?<prefix><experiment_id>=1.
    Le préfixe est issu de la config QA (ex: 'dwft_').
    N'influence que la **clé de cache** (suffixe '|qa'), pas la résolution.
    """
    try:
        prefix = (get_qa_policy() or {}).get("preview_param_prefix", "dwft_")
        return request.GET.get(f"{prefix}{experiment_id}") == "1"
    except Exception:
        return False

def apply_preview_override(request, flag: str) -> Optional[str]:
    # Placeholder (non utilisé P0)
    return None

def is_flag_active(flag: str, user=None) -> bool:
    # Placeholder P0: pas de rollout réel (toujours False => A par défaut)
    return False
