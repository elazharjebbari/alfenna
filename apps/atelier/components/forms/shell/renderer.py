# apps/atelier/components/forms/shell/renderer.py
from __future__ import annotations
from typing import Any, Dict
from django.template.loader import render_to_string

def render(hydrated_ctx: Dict[str, Any], request) -> Dict[str, Any]:
    wizard_html = hydrated_ctx.get("wizard_html")

    if not wizard_html:
        # Secours: on tente de générer depuis child.config_json
        child = hydrated_ctx.get("child") or {}
        cfg = child.get("config_json") or "{}"
        wizard_html = render_to_string(
            "components/forms/wizard.html",
            {"config_json": cfg},
            request=request,
        )

    html = render_to_string(
        "components/forms/shell.html",
        {
            "display": hydrated_ctx.get("display") or "inline",
            "title_html": hydrated_ctx.get("title_html") or "",
            "subtitle_html": hydrated_ctx.get("subtitle_html") or "",
            "wizard_html": wizard_html,  # legacy branch
            "use_child_compose": bool(hydrated_ctx.get("use_child_compose", False)),
            "children": hydrated_ctx.get("children") or {},
        },
        request=request,
    )
    return {"html": html, "assets": hydrated_ctx.get("assets") or {"js": [], "css": [], "head": []}}
