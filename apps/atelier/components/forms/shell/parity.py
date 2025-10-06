# apps/atelier/components/forms/shell/parity.py
from __future__ import annotations
import json
import re
from typing import Dict, Any, Tuple, List

_SCRIPT_RE = re.compile(
    r'<script[^>]*data-ff-config[^>]*>(?P<payload>.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)

def _extract_config_json(html: str) -> Tuple[dict | None, str]:
    if not isinstance(html, str):
        return None, ""
    m = _SCRIPT_RE.search(html or "")
    if not m:
        return None, ""
    raw = (m.group("payload") or "").strip()
    try:
        return json.loads(raw), raw
    except Exception:
        return None, raw

def _has(html: str, needle: str) -> bool:
    return isinstance(html, str) and (needle in html)

def _has_any(html: str, needles: list[str]) -> bool:
    if not isinstance(html, str):
        return False
    return any(n in html for n in needles)

def check_parity(html_compose: str, html_legacy: str) -> Dict[str, Any]:
    """
    Parité fonctionnelle (invariants) entre compose et legacy :
      - data-ff-root
      - data-ff-step="1" et "2"
      - dernière étape : data-ff-step="3" **ou** data-ff-step="done"
      - <script data-ff-config> + JSON parseable et identique
    """
    details: List[str] = []
    ok = True

    # Invariants communs
    for tag, ndl in [
        ("root", 'data-ff-root'),
        ("step1", 'data-ff-step="1"'),
        ("step2", 'data-ff-step="2"'),
        ("cfg_script", 'data-ff-config'),
    ]:
        c_ok = _has(html_compose, ndl)
        l_ok = _has(html_legacy, ndl)
        if not c_ok or not l_ok:
            ok = False
            details.append(f"missing:{tag}: compose={c_ok} legacy={l_ok}")

    # Étape finale acceptée sous forme "3" OU "done"
    final_needles = ['data-ff-step="3"', 'data-ff-step="done"']
    c_final = _has_any(html_compose, final_needles)
    l_final = _has_any(html_legacy, final_needles)
    if not c_final or not l_final:
        ok = False
        details.append(f'missing:final_step(3_or_done): compose={c_final} legacy={l_final}')

    # Config JSON identique et parseable
    c_json, c_raw = _extract_config_json(html_compose)
    l_json, l_raw = _extract_config_json(html_legacy)

    if not c_raw:
        ok = False; details.append("config_script_absent_compose")
    if not l_raw:
        ok = False; details.append("config_script_absent_legacy")

    if c_raw and l_raw:
        if c_json is None:
            ok = False; details.append("config_json_unparseable_compose")
        if l_json is None:
            ok = False; details.append("config_json_unparseable_legacy")
        if c_json is not None and l_json is not None and c_json != l_json:
            ok = False; details.append("config_json_differs")

    return {"ok": ok, "details": [d for d in details if d]}
