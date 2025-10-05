from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Tuple

from celery.exceptions import Retry
from django.utils import timezone
from smtplib import SMTPRecipientsRefused
from unittest.mock import patch

from apps.messaging.models import EmailAttempt, OutboxEmail
from apps.messaging.tasks import send_outbox_email


@dataclass
class ScenarioResult:
    label: str
    description: str
    smtp_payload: Dict[str, Tuple[int, bytes]] | None


SCENARIOS: Dict[str, ScenarioResult] = {
    "success": ScenarioResult(
        label="Succès",
        description="Envoi nominal → statut SENT",
        smtp_payload=None,
    ),
    "bounce": ScenarioResult(
        label="Quota bounce",
        description="Erreur 5.4.6 Sender Hourly Bounce Limit Exceeded",
        smtp_payload={
            "cli-reset@example.com": (550, b"5.4.6 Sender Hourly Bounce Limit Exceeded - smoke"),
        },
    ),
    "invalid": ScenarioResult(
        label="Adresse invalide",
        description="Erreur 5.1.1 User unknown",
        smtp_payload={
            "cli-reset@example.com": (550, b"5.1.1 User unknown"),
        },
    ),
}


def _parse_args(args: Iterable[str]) -> Dict[str, str]:
    options: Dict[str, str] = {}
    for arg in args:
        if not arg:
            continue
        if "=" in arg:
            key, value = arg.split("=", 1)
            options[key.strip().lstrip("-")] = value.strip()
        else:
            options[arg.strip().lstrip("-")] = "1"
    return options


def _patch_backend(payload: Dict[str, Tuple[int, bytes]] | None):
    if payload is None:
        class _HappyBackend:
            def send_messages(self, messages):  # pragma: no cover - used for smoke only
                return 1

        return patch("apps.messaging.tasks.get_connection", return_value=_HappyBackend())

    class _FailingBackend:
        def send_messages(self, messages):  # pragma: no cover - used for smoke only
            raise SMTPRecipientsRefused(payload)

    return patch("apps.messaging.tasks.get_connection", return_value=_FailingBackend())


def _print_header(title: str) -> None:
    print("\n===", title, "===")


def _print_state(outbox: OutboxEmail) -> None:
    outbox.refresh_from_db()
    print(
        f"Outbox #{outbox.id} — status={outbox.status} attempts={outbox.attempt_count} "
        f"next_attempt_at={outbox.next_attempt_at} last_error_code={outbox.last_error_code or '-'}"
    )
    attempts = EmailAttempt.objects.filter(outbox=outbox).order_by("created_at")
    for attempt in attempts:
        print(
            f"  • Attempt {attempt.id} → {attempt.status}"
            + (f" ({attempt.error_message[:120]})" if attempt.error_message else "")
        )


def run(*script_args):
    """Smoke-test helper for the password reset e-mail pipeline."""

    options = _parse_args(script_args)
    scenario_key = options.get("scenario", "bounce")
    scenario = SCENARIOS.get(scenario_key)
    if scenario is None:
        available = ", ".join(sorted(SCENARIOS.keys()))
        raise SystemExit(f"Unknown scenario '{scenario_key}'. Try one of: {available}")

    _print_header("Password reset smoke")
    print(f"Scenario: {scenario_key} — {scenario.label}")
    print(f"Description: {scenario.description}")

    unique_suffix = f"{scenario_key}-{int(timezone.now().timestamp())}"
    dedup_key = f"reset-smoke-{unique_suffix}"

    OutboxEmail.objects.filter(dedup_key=dedup_key).delete()

    flow_id = f"flow-{unique_suffix}"
    OutboxEmail.objects.filter(flow_id=flow_id).delete()

    outbox = OutboxEmail.objects.create(
        namespace="accounts",
        purpose="password_reset",
        flow_id=flow_id,
        dedup_key=dedup_key,
        to=["cli-reset@example.com"],
        template_slug="accounts/reset",
        template_version=1,
        rendered_subject="Reset Smoke",
        rendered_text="Voici votre lien",
        rendered_html="<p>Voici votre lien</p>",
        status=OutboxEmail.Status.QUEUED,
        scheduled_at=timezone.now(),
        priority=100,
        metadata={"smoke": scenario_key},
    )

    print(f"Created outbox #{outbox.id} with flow_id={flow_id}")

    backend_patch = _patch_backend(scenario.smtp_payload)

    with backend_patch:
        try:
            send_outbox_email.apply(args=[outbox.id])
        except Retry as exc:  # bounce scenario triggers celery retry
            print(f"→ Celery scheduled a retry: {exc}")
        except SMTPRecipientsRefused as exc:  # pragma: no cover - defensive
            print(f"→ SMTP rejection propagated: {exc}")

    _print_state(outbox)
    print("=== END ===\n")
