"""Ensure the buyer_access test user exists (optional entitlement)."""
from __future__ import annotations

import argparse
from typing import Iterable, List

from django.contrib.auth import get_user_model
from django.db import transaction

from apps.catalog.models.models import Course
from apps.billing.models import Entitlement
from apps.common.runscript_harness import binary_harness

USERNAME = "buyer_access"
DEFAULT_EMAIL = "buyer_access@example.com"
DEFAULT_PASSWORD = "Password-2025"
COURSE_SLUG = "fabrication-de-bougie"


def _coerce_args(script_args: Iterable[str] | None) -> List[str]:
    if script_args is None:
        return []
    if not isinstance(script_args, (list, tuple)):
        tokens = str(script_args).split()
    else:
        tokens = list(script_args)

    coerced: List[str] = []
    for token in tokens:
        if token.startswith("--"):
            coerced.append(token)
            continue
        if "=" in token:
            key, value = token.split("=", 1)
            coerced.append(f"--{key}")
            if value:
                coerced.append(value)
        else:
            coerced.append(token)
    return coerced


def _parse_args(script_args: Iterable[str] | None):
    parser = argparse.ArgumentParser(description="Ensure the buyer_access test user exists")
    parser.add_argument("--password", dest="password", default=DEFAULT_PASSWORD)
    parser.add_argument("--email", dest="email", default=DEFAULT_EMAIL)
    parser.add_argument("--entitle", dest="entitle", action="store_true")
    tokens = _coerce_args(script_args)
    return parser.parse_args(tokens)


@binary_harness
@transaction.atomic
def run(*args, **kwargs):
    raw_args: Iterable[str] | None = kwargs.get("script_args")
    if raw_args is None:
        raw_args = args
    args = _parse_args(raw_args)
    password = args.password or DEFAULT_PASSWORD
    email = args.email or DEFAULT_EMAIL

    User = get_user_model()
    user, created = User.objects.get_or_create(
        username=USERNAME,
        defaults={"email": email, "is_active": True},
    )

    updates = {"created": created, "password_updated": False, "entitlement_created": False}

    if user.email != email:
        user.email = email
        updates["email_updated"] = True
    else:
        updates["email_updated"] = False

    if not user.check_password(password):
        user.set_password(password)
        updates["password_updated"] = True

    if updates["email_updated"] or updates["password_updated"] or created:
        user.is_active = True
        user.save()

    if args.entitle:
        course = Course.objects.filter(slug=COURSE_SLUG).first()
        if not course:
            return {
                "ok": False,
                "name": "ensure_buyer_fixture",
                "duration": 0.0,
                "logs": [
                    {
                        "error": f"Course '{COURSE_SLUG}' introuvable",
                        "user_created": created,
                    }
                ],
            }
        _, ent_created = Entitlement.objects.get_or_create(user=user, course=course)
        updates["entitlement_created"] = ent_created
    else:
        # Ensure no lingering entitlement when not requested
        Entitlement.objects.filter(user=user, course__slug=COURSE_SLUG).delete()

    summary = {
        "username": USERNAME,
        "email": user.email,
        "created": updates["created"],
        "password_updated": updates["password_updated"],
        "email_updated": updates["email_updated"],
        "entitlement_action": "created" if updates["entitlement_created"] else ("removed" if not args.entitle else "unchanged"),
    }

    return {
        "ok": True,
        "name": "ensure_buyer_fixture",
        "duration": 0.0,
        "logs": [summary],
    }
