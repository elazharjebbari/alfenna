from __future__ import annotations
import json
from django.core.management.base import CommandError
from django.template.loader import render_to_string
from apps.atelier.components.discovery import discover
from apps.atelier.components.registry import get as get_component, NamespaceComponentMissing
from apps.atelier.compose.hydration import load as hydrate
from apps.atelier.components.contracts import validate as validate_contract
from types import SimpleNamespace
from apps.common.runscript_harness import binary_harness

@binary_harness
def run():
    print("== content_training smoke ==")
    count, warns = discover(override=True)
    try:
        comp = get_component("training/content_training", namespace="core", fallback=False)
    except NamespaceComponentMissing as exc:
        raise CommandError(str(exc))

    # fake request
    req = SimpleNamespace()
    req.headers = {"Accept-Language":"fr"}
    req.META = {"HTTP_USER_AGENT":"smoke"}
    req.COOKIES = {}
    req.GET = {}
    req.user = SimpleNamespace(is_authenticated=False, first_name="")
    req.site_version = "core"

    # A) hydrate manifest-only
    ctxA = hydrate("training/content_training", req, {}, namespace="core")
    validate_contract("training/content_training", ctxA, namespace="core")
    htmlA = render_to_string(comp["template"], ctxA)
    ok_price = str(ctxA.get("price")) in htmlA
    ok_bullets = htmlA.count("fa fa-circle") >= 5
    print("[A] price in HTML:", ok_price, " bullets:", ok_bullets)
    if not (ok_price and ok_bullets):
        raise CommandError("Rendering KO (manifest-only).")

    # B) override params
    ctxB = hydrate("training/content_training", req, {"price": 123, "videos_count": 99, "modules_count": 9}, namespace="core")
    htmlB = render_to_string(comp["template"], ctxB)
    if "123" not in htmlB or "99" not in htmlB or "9 modules" not in htmlB:
        raise CommandError("Overrides non pris en compte.")

    print("== OK : content_training rend correctement (manifest + overrides) ==")
