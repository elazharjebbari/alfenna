from __future__ import annotations

from types import SimpleNamespace

from django.test import RequestFactory

from apps.atelier.compose.response import render_base
from apps.common.runscript_harness import binary_harness


@binary_harness
def run():
    factory = RequestFactory()
    request = factory.get("/")
    request._segments = SimpleNamespace(
        lang="ar",
        device="desktop",
        consent="Y",
        source="",
        campaign="",
        qa=False,
    )

    page_ctx = {"id": "", "site_version": "core", "slots": {}}
    response = render_base(page_ctx, {}, {"css": [], "js": [], "head": []}, request)
    response.render()

    context = response.context_data
    css_assets = context.get("page_assets", {}).get("css", [])

    ok = context.get("lang_dir") == "rtl" and context.get("is_rtl") is True
    ok = ok and any("rtl" in asset for asset in css_assets)

    logs = {
        "lang_code": context.get("lang_code"),
        "lang_dir": context.get("lang_dir"),
        "is_rtl": context.get("is_rtl"),
        "css_assets": css_assets,
    }

    return {"ok": ok, "name": "rtl_layout_smoke", "logs": [logs]}
