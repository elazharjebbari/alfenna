"""Diagnostic helper around superuser creation and email uniqueness."""
from __future__ import annotations

import os
from typing import Dict

from django.contrib.auth import get_user_model
from django.db.models import Count
from django.db.models.functions import Lower


def _parse_args(args: tuple[str, ...]) -> Dict[str, str]:
    params: Dict[str, str] = {}
    for raw in args:
        if not raw:
            continue
        if "=" in raw:
            key, value = raw.split("=", 1)
            params[key.strip()] = value.strip()
        else:
            params[raw.strip()] = "1"
    return params


def run(*script_args):
    params = _parse_args(script_args)
    create_flag = params.get("create", "false").lower() in {"1", "true", "yes"}

    username = os.getenv("DJANGO_SUPERUSER_USERNAME", "")
    email = os.getenv("DJANGO_SUPERUSER_EMAIL", "")
    password = os.getenv("DJANGO_SUPERUSER_PASSWORD", "")

    User = get_user_model()

    total_users = User.objects.count()
    blank_email_count = User.objects.filter(email="").count()
    duplicate_rows = (
        User.objects.exclude(email="")
        .annotate(email_lower=Lower("email"))
        .values("email_lower")
        .annotate(total=Count("id"))
        .filter(total__gt=1)
        .order_by("-total")
    )

    print("=== Superuser diagnostics ===")
    print(f"Total users: {total_users}")
    print(f"Users with blank email: {blank_email_count}")
    if duplicate_rows:
        print("Duplicate emails (case-insensitive):")
        for row in duplicate_rows:
            email_lower = row["email_lower"]
            total = row["total"]
            print(f"  - {email_lower!r}: {total}")
    else:
        print("No duplicate emails detected (case-insensitive check).")

    print("\nEnvironment credentials (if any):")
    print(f"  DJANGO_SUPERUSER_USERNAME={username or '(empty)'}")
    print(f"  DJANGO_SUPERUSER_EMAIL={email or '(empty)'}")
    print(f"  DJANGO_SUPERUSER_PASSWORD={'***' if password else '(empty)'}")

    if not create_flag:
        print("\nTip: pass create=true via --script-args to attempt creation with the env variables.")
        return

    print("\nAttempting superuser creation…")
    if not username or not email or not password:
        print("ERROR: username/email/password env vars must be set when create=true.")
        return

    if User.objects.filter(email__iexact=email).exists():
        print(f"ERROR: a user already exists with email {email!r} (case-insensitive match).")
        return

    if User.objects.filter(username=username).exists():
        print(f"ERROR: a user already exists with username {username!r}.")
        return

    try:
        User.objects.create_superuser(username=username, email=email, password=password)
    except Exception as exc:  # pylint: disable=broad-except
        print(f"Superuser creation failed: {exc!r}")
        return

    print("Superuser created successfully.")

