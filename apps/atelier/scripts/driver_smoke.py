"""Smoke test ensuring driver.js is no longer injected."""
from __future__ import annotations

from types import SimpleNamespace

from django.test import RequestFactory

from apps.atelier.compose import pipeline

FORBIDDEN_TOKENS = ("driver", "data-tutorial", "shepherd")
SLOT_IDS = ("before_after_wipe", "program_roadmap")


def _build_request():
    factory = RequestFactory()
    request = factory.get("/")
    request.site_version = "core"
    request._segments = SimpleNamespace(lang="fr", device="desktop", consent="N", source="", campaign="", qa=False)
    request.GET = {}
    request.COOKIES = {}
    request.META = {
        "HTTP_USER_AGENT": "driver-smoke",
        "SERVER_NAME": "testserver",
        "SERVER_PORT": "80",
        "wsgi.url_scheme": "http",
    }
    request.headers = {"Accept-Language": "fr"}
    request.user = SimpleNamespace(is_authenticated=False)
    request.get_host = lambda: "testserver"
    return request


def run():
    request = _build_request()
    page_ctx = pipeline.build_page_spec("online_home", request)
    ok = True

    for slot_id in SLOT_IDS:
        slot = dict(page_ctx["slots"][slot_id])
        slot["cache"] = False
        html = pipeline.render_slot_fragment(page_ctx, slot, request)["html"].lower()
        leakage = [token for token in FORBIDDEN_TOKENS if token in html]
        if leakage:
            ok = False
            print(f"[KO] {slot_id}: found tokens {', '.join(leakage)}")
        else:
            print(f"[OK] {slot_id}: clean")

    if not ok:
        raise SystemExit(1)

    print("Driver auto-tour assets absent from before_after/wipe and program/roadmap.")
