"""Runs scripted access verification for the buyer_access test user."""
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import Client

from apps.accounts.scripts import ensure_buyer_fixture
from apps.catalog.models.models import Course
from apps.content.models import Lecture, LectureVideoVariant, LanguageCode
from apps.common.runscript_harness import binary_harness
from apps.billing.models import Entitlement

COURSE_SLUG = "fabrication-de-bougie"
PASSWORD = "Password-2025"
USERNAME = "buyer_access"
FREE_PREFIXES = ["1", "1-1", "2", "2-1"]
PREMIUM_PREFIX = "3"
RANGE_HEADER = "bytes=0-1023"
PREFIX_PATTERN = re.compile(r"^(?P<prefix>\d+(?:-\d+)?)")
SUFFIX_PATTERN = re.compile(r"[_-][A-Za-z0-9]{4,}$")


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
    parser = argparse.ArgumentParser(description="Verify access for buyer_access user")
    parser.add_argument("--password", dest="password", default=PASSWORD)
    tokens = _coerce_args(script_args)
    return parser.parse_args(tokens)


@dataclass
class CheckResult:
    prefix: str
    lang: str
    status: int
    expected: str
    content_language: Optional[str]
    vary: Optional[str]
    notes: Optional[str] = None


def _strip_random_suffix(stem: str) -> str:
    candidate = stem
    while True:
        match = SUFFIX_PATTERN.search(candidate)
        if not match:
            break
        candidate = candidate[: match.start()]
    return candidate


def _prefix_from_stems(stems: Iterable[str]) -> Optional[str]:
    for stem in stems:
        if not stem:
            continue
        match = PREFIX_PATTERN.match(stem)
        if match:
            return match.group("prefix")
        cleaned = _strip_random_suffix(stem)
        match = PREFIX_PATTERN.match(cleaned)
        if match:
            return match.group("prefix")
    return None


def _prefix_map(course: Course) -> Dict[str, Lecture]:
    mapping: Dict[str, Lecture] = {}
    lectures = Lecture.objects.filter(course=course).prefetch_related("video_variants", "section")
    for lecture in lectures:
        stems: List[str] = []
        for variant in lecture.video_variants.all():
            stems.append(Path(variant.storage_path).stem)
        if lecture.video_path:
            stems.append(Path(lecture.video_path).stem)
        prefix = _prefix_from_stems(stems)
        if prefix:
            mapping[prefix] = lecture
    return mapping


def _head_stream(client: Client, lecture_id: int, lang: str) -> Client:
    return client.head(
        f"/learning/stream/{lecture_id}/",
        {"lang": lang},
        HTTP_RANGE=RANGE_HEADER,
    )


def _check_stream(client: Client, lecture: Lecture, lang: str, expected: str) -> CheckResult:
    response = _head_stream(client, lecture.id, lang)
    expected_label = expected
    note: Optional[str] = None

    if expected == "allowed":
        assert response.status_code == 206, f"Expected 206 for lecture {lecture.id} lang {lang}, got {response.status_code}"
        assert response["Content-Language"].lower() == lang.replace("_", "-").lower()
        assert "Accept-Language" in (response.get("Vary", "")), "Vary header must include Accept-Language"
        assert response["Accept-Ranges"] == "bytes"
        assert response["Content-Range"].startswith("bytes 0-"), "Invalid Content-Range"
    elif expected == "blocked":
        assert response.status_code in (302, 403), f"Expected 302/403 for lecture {lecture.id}, got {response.status_code}"
    else:
        note = f"Unknown expectation '{expected}'"

    return CheckResult(
        prefix=_prefix_from_stems([Path(lecture.video_path or "").stem]) or "?",
        lang=lang,
        status=response.status_code,
        expected=expected_label,
        content_language=response.get("Content-Language"),
        vary=response.get("Vary"),
        notes=note,
    )


def _collect_results(checks: List[CheckResult]) -> List[Dict[str, Optional[str]]]:
    return [
        {
            "prefix": check.prefix,
            "lang": check.lang,
            "status": check.status,
            "expected": check.expected,
            "content_language": check.content_language,
            "vary": check.vary,
            "notes": check.notes,
        }
        for check in checks
    ]


def _ensure_user(password: str, with_entitlement: bool):
    args = [f"password={password}"]
    if with_entitlement:
        args.append("--entitle")
    ensure_buyer_fixture.run(script_args=args)


def _login_client(client: Client, password: str) -> None:
    success = client.login(username=USERNAME, password=password)
    assert success, "Login failed for buyer_access"


@binary_harness
@transaction.atomic
def run(*args, **kwargs):
    raw_args: Iterable[str] | None = kwargs.get("script_args")
    if raw_args is None:
        raw_args = args
    parsed = _parse_args(raw_args)
    password = parsed.password or PASSWORD

    course = Course.objects.filter(slug=COURSE_SLUG).first()
    if not course:
        return {
            "ok": False,
            "name": "verify_access_buyer",
            "duration": 0.0,
            "logs": [f"Course '{COURSE_SLUG}' introuvable. Lance d'abord le seed."],
        }

    lecture_map = _prefix_map(course)
    missing_prefixes = [prefix for prefix in FREE_PREFIXES + [PREMIUM_PREFIX] if prefix not in lecture_map]
    if missing_prefixes:
        return {
            "ok": False,
            "name": "verify_access_buyer",
            "duration": 0.0,
            "logs": [
                {
                    "error": f"Préfixes manquants dans le cours: {', '.join(missing_prefixes)}",
                }
            ],
        }

    _ensure_user(password, with_entitlement=False)
    User = get_user_model()
    user = User.objects.get(username=USERNAME)
    Entitlement.objects.filter(user=user, course=course).delete()

    client = Client()
    _login_client(client, password)

    pre_checks: List[CheckResult] = []

    for prefix in FREE_PREFIXES:
        lecture = lecture_map[prefix]
        # Always test FR
        pre_checks.append(_check_stream(client, lecture, "fr_FR", expected="allowed"))
        if lecture.video_variants.filter(lang=LanguageCode.AR_MA).exists():
            pre_checks.append(_check_stream(client, lecture, "ar_MA", expected="allowed"))

    premium_lecture = lecture_map.get(PREMIUM_PREFIX)
    if premium_lecture:
        response = _check_stream(client, premium_lecture, "fr_FR", expected="blocked")
        pre_checks.append(response)

    # Scenario 2 - with entitlement
    _ensure_user(password, with_entitlement=True)
    client.logout()
    _login_client(client, password)

    post_checks: List[CheckResult] = []

    for prefix in FREE_PREFIXES:
        lecture = lecture_map[prefix]
        post_checks.append(_check_stream(client, lecture, "fr_FR", expected="allowed"))
        if lecture.video_variants.filter(lang=LanguageCode.AR_MA).exists():
            post_checks.append(_check_stream(client, lecture, "ar_MA", expected="allowed"))

    if premium_lecture:
        post_checks.append(_check_stream(client, premium_lecture, "fr_FR", expected="allowed"))
        if premium_lecture.video_variants.filter(lang=LanguageCode.AR_MA).exists():
            post_checks.append(_check_stream(client, premium_lecture, "ar_MA", expected="allowed"))

    summary = {
        "course": COURSE_SLUG,
        "user": USERNAME,
        "pre_entitlement": _collect_results(pre_checks),
        "post_entitlement": _collect_results(post_checks),
    }

    # Console log
    print("=== BUYER ACCESS CHECK ===")
    for label, checks in (("PRE", pre_checks), ("POST", post_checks)):
        for check in checks:
            print(
                f"[{label}] prefix={check.prefix:<4} lang={check.lang:<5} status={check.status:<3} expected={check.expected:<8} "
                f"CL={check.content_language or '-':<6} Vary={check.vary or '-'}"
            )

    return {
        "ok": True,
        "name": "verify_access_buyer",
        "duration": 0.0,
        "logs": [summary],
    }


# Expose helper for test imports
run_script = run
