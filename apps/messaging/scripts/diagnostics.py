from __future__ import annotations

from collections import OrderedDict
from datetime import timedelta
from typing import Dict, Iterable, List

from django.db.models import Count, Q
from django.utils import timezone

from apps.messaging.models import Campaign, CampaignRecipient, OutboxEmail


def _status_summary(label: str, counts: Dict[str, int], statuses: Iterable[str]) -> str:
    ordered = OrderedDict((status, counts.get(status, 0)) for status in statuses)
    formatted = ", ".join(f"{status}:{total}" for status, total in ordered.items())
    return f"{label}: {formatted or 'Ø'}"


def _top_errors(since) -> List[str]:
    rows = (
        OutboxEmail.objects.filter(last_error_at__gte=since, last_error_message__gt="")
        .values("last_error_message")
        .annotate(total=Count("id"))
        .order_by("-total")[:5]
    )
    if not rows:
        return ["Top erreurs SMTP (7j): Ø"]
    entries = [
        f"{row['total']}× {row['last_error_message'][:80]}"
        for row in rows
    ]
    return ["Top erreurs SMTP (7j): " + " | ".join(entries)]


def _top_templates(since) -> List[str]:
    rows = (
        OutboxEmail.objects.filter(created_at__gte=since)
        .values("namespace", "purpose", "template_slug")
        .annotate(total=Count("id"))
        .order_by("-total")[:5]
    )
    if not rows:
        return ["Top templates (7j): Ø"]
    entries = [
        f"{row['total']}× {row['namespace']}/{row['template_slug']} ({row['purpose']})"
        for row in rows
    ]
    return ["Top templates (7j): " + " | ".join(entries)]


def _campaign_overview(reference: timezone.datetime) -> List[str]:
    statuses = [
        Campaign.Status.SCHEDULED,
        Campaign.Status.RUNNING,
        Campaign.Status.PAUSED,
    ]
    qs = Campaign.objects.filter(status__in=statuses).annotate(
        pending_total=Count("recipients", filter=Q(recipients__status=CampaignRecipient.Status.PENDING)),
        queued_total=Count("recipients", filter=Q(recipients__status=CampaignRecipient.Status.QUEUED)),
        sent_total=Count("recipients", filter=Q(recipients__status=CampaignRecipient.Status.SENT)),
    )
    results = []
    for campaign in qs.order_by("scheduled_at"):
        desc = (
            f"{campaign.slug} [{campaign.status}] · batch={campaign.batch_size} · dry_run={campaign.dry_run} "
            f"· pending={getattr(campaign, 'pending_total', 0)} · queued={getattr(campaign, 'queued_total', 0)} "
            f"· sent={getattr(campaign, 'sent_total', 0)}"
        )
        results.append(desc)
    if not results:
        return ["Campagnes actives: Ø"]
    return ["Campagnes actives:"] + [f" - {line}" for line in results]


def run(now: timezone.datetime | None = None) -> Dict[str, object]:
    """Generate observability counters for Outbox and campaigns."""
    reference = now or timezone.now()
    logs: List[str] = []

    statuses = [choice[0] for choice in OutboxEmail.Status.choices]

    day_ago = reference - timedelta(hours=24)
    week_ago = reference - timedelta(days=7)

    counts_24h = {
        status: OutboxEmail.objects.filter(status=status, scheduled_at__gte=day_ago).count()
        for status in statuses
    }
    counts_7d = {
        status: OutboxEmail.objects.filter(status=status, scheduled_at__gte=week_ago).count()
        for status in statuses
    }

    logs.append(_status_summary("Outbox (24h)", counts_24h, statuses))
    logs.append(_status_summary("Outbox (7j)", counts_7d, statuses))
    logs.extend(_top_errors(week_ago))
    logs.extend(_top_templates(week_ago))
    logs.extend(_campaign_overview(reference))

    return {"ok": True, "logs": logs}
