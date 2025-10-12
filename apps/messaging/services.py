"""Service layer orchestrating template rendering and outbox creation."""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from celery import current_app
from django.conf import settings
from django.db import IntegrityError, transaction
from django.template import Context, Template, TemplateDoesNotExist
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags
from django.utils.translation import get_language

from .exceptions import DeduplicationConflictError, TemplateNotFoundError
from .models import EmailTemplate, OutboxEmail


log = logging.getLogger("messaging.services")


@dataclass(frozen=True)
class EmailComposition:
    """Rendered e-mail pieces ready for enqueueing."""

    subject: str
    html_body: str
    text_body: str
    context: Dict[str, Any]
    template_slug: str
    template_version: int


class TemplateService:
    """Resolve and render templates stored in the database."""

    @staticmethod
    def resolve(slug: str, locale: str) -> EmailTemplate:
        template = EmailTemplate.objects.latest_for(slug, locale)
        if template is None:
            raise TemplateNotFoundError(f"No active template for slug='{slug}' locale='{locale}'")
        return template

    @staticmethod
    def render(template: EmailTemplate, context: Optional[Dict[str, Any]] = None) -> EmailComposition:
        ctx = dict(context or {})
        # Render subject separately to avoid HTML escaping differences.
        subject_template = Template(template.subject)
        html_template = Template(template.html_template)
        text_template = Template(template.text_template)

        subj_ctx = Context(ctx)
        subject = subject_template.render(subj_ctx).strip()
        html_body = html_template.render(Context(ctx))
        text_body = text_template.render(Context(ctx))

        return EmailComposition(
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            context=ctx,
            template_slug=template.slug,
            template_version=template.version,
        )


class EmailService:
    """Create OutboxEmail rows in an idempotent fashion."""

    @staticmethod
    def _normalize_language_code(code: Optional[str]) -> Optional[str]:
        if not code:
            return None
        normalized = str(code).strip()
        if not normalized:
            return None
        return normalized.replace("_", "-").lower()

    @classmethod
    def _preferred_languages(cls, *, language: Optional[str], user: Any, locale: Optional[str]) -> List[str]:
        candidates: List[Optional[str]] = [language]
        profile = getattr(user, "profile", None) if user is not None else None
        profile_locale = getattr(profile, "locale", None)
        if profile_locale:
            candidates.append(profile_locale)
        candidates.append(locale)
        current_lang = get_language()
        if current_lang:
            candidates.append(current_lang)
        candidates.append(getattr(settings, "LANGUAGE_CODE", None))
        for lang_code, _ in getattr(settings, "LANGUAGES", []):
            candidates.append(lang_code)
        candidates.extend(["fr", "en"])

        ordered: List[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            normalized = cls._normalize_language_code(candidate)
            if normalized and normalized not in seen:
                seen.add(normalized)
                ordered.append(normalized)
        return ordered

    @staticmethod
    def _template_base_path(namespace: str, template_slug: str) -> tuple[str, str]:
        slug_parts = [part for part in template_slug.split("/") if part]
        if slug_parts:
            slug_name = slug_parts[-1]
            dir_parts = slug_parts[:-1]
        else:
            slug_name = template_slug
            dir_parts: List[str] = []
        if namespace and (not dir_parts or dir_parts[0] != namespace):
            dir_parts = [namespace, *dir_parts]
        base_path = "/".join(["emails", *dir_parts, slug_name])
        return base_path, slug_name

    @classmethod
    def _render_filesystem_template(
        cls,
        namespace: str,
        template_slug: str,
        language: str,
        context: Dict[str, Any],
    ) -> Optional[EmailComposition]:
        base_path, slug_name = cls._template_base_path(namespace, template_slug)
        html_template_name = f"{base_path}.{language}.html"
        ctx = dict(context)
        try:
            html_body = render_to_string(html_template_name, ctx)
        except TemplateDoesNotExist:
            return None
        try:
            text_body = render_to_string(f"{base_path}.{language}.txt", ctx)
        except TemplateDoesNotExist:
            text_body = strip_tags(html_body)
        try:
            subject = render_to_string(f"{base_path}.{language}.subject.txt", ctx).strip()
        except TemplateDoesNotExist:
            subject = ctx.get("email_subject") or ctx.get("subject") or slug_name.replace("_", " ").title()
        return EmailComposition(
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            context=ctx,
            template_slug=f"fs:{base_path}",
            template_version=1,
        )

    @staticmethod
    def _serialise_addresses(addresses: Optional[Iterable[str]]) -> List[str]:
        if not addresses:
            return []
        return [str(addr).strip() for addr in addresses if str(addr).strip()]

    @staticmethod
    def _make_dedup_key(
        *,
        namespace: str,
        purpose: str,
        primary_recipient: str,
        template_slug: str,
        template_version: int,
        context: Dict[str, Any],
        explicit_key: Optional[str] = None,
    ) -> str:
        if explicit_key:
            return explicit_key
        payload = {
            "namespace": namespace,
            "purpose": purpose,
            "recipient": primary_recipient,
            "template": f"{template_slug}:{template_version}",
            "context": context,
        }
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @classmethod
    def compose_and_enqueue(
        cls,
        *,
        namespace: str,
        purpose: str,
        template_slug: str,
        to: Iterable[str],
        locale: str = "fr",
        language: Optional[str] = None,
        user: Optional[Any] = None,
        context: Optional[Dict[str, Any]] = None,
        dedup_key: Optional[str] = None,
        scheduled_at: Optional[datetime] = None,
        priority: int = 100,
        cc: Optional[Iterable[str]] = None,
        bcc: Optional[Iterable[str]] = None,
        reply_to: Optional[Iterable[str]] = None,
        headers: Optional[Dict[str, Any]] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        subject_override: Optional[str] = None,
        flow_id: Optional[str] = None,
    ) -> OutboxEmail:
        recipients = cls._serialise_addresses(to)
        if not recipients:
            raise ValueError("At least one recipient must be provided")

        context_data = dict(context or {})
        preferred_languages = cls._preferred_languages(language=language, user=user, locale=locale)

        composition: Optional[EmailComposition] = None
        resolved_locale: Optional[str] = None
        for lang in preferred_languages:
            composition = cls._render_filesystem_template(namespace, template_slug, lang, context_data)
            if composition is not None:
                resolved_locale = lang
                break

        if composition is None:
            fallback_locale = preferred_languages[0] if preferred_languages else cls._normalize_language_code(locale) or settings.LANGUAGE_CODE
            template = TemplateService.resolve(template_slug, fallback_locale or "fr")
            composition = TemplateService.render(template, context_data)
            resolved_locale = template.locale
        else:
            template = None

        subject = subject_override or composition.subject
        computed_key = cls._make_dedup_key(
            namespace=namespace,
            purpose=purpose,
            primary_recipient=recipients[0],
            template_slug=composition.template_slug,
            template_version=composition.template_version,
            context=dict(composition.context),
            explicit_key=dedup_key,
        )

        defaults = {
            "purpose": purpose,
            "flow_id": flow_id or "",
            "to": recipients,
            "cc": cls._serialise_addresses(cc),
            "bcc": cls._serialise_addresses(bcc),
            "reply_to": cls._serialise_addresses(reply_to),
            "locale": resolved_locale or locale or settings.LANGUAGE_CODE,
            "template_slug": composition.template_slug,
            "template_version": composition.template_version,
            "subject_override": subject_override or "",
            "rendered_subject": subject,
            "rendered_html": composition.html_body,
            "rendered_text": composition.text_body,
            "context": composition.context,
            "headers": headers or {},
            "attachments": attachments or [],
            "scheduled_at": scheduled_at or timezone.now(),
            "priority": priority,
            "metadata": metadata or {},
        }

        try:
            with transaction.atomic():
                outbox, created = OutboxEmail.objects.get_or_create(
                    namespace=namespace,
                    dedup_key=computed_key,
                    defaults=defaults,
                )
                if created:
                    transaction.on_commit(schedule_outbox_drain)
                elif flow_id and not outbox.flow_id:
                    outbox.flow_id = flow_id
                    outbox.save(update_fields=["flow_id", "updated_at"])
                return outbox
        except IntegrityError as exc:  # pragma: no cover - defensive
            raise DeduplicationConflictError("Outbox deduplication conflict") from exc

def schedule_outbox_drain() -> None:
    """Schedule the Celery drain task, working even when running eagerly."""

    try:
        task = current_app.tasks.get("apps.messaging.tasks.drain_outbox_batch")
        if task is None:
            from apps.messaging.tasks import drain_outbox_batch  # inline import to avoid circular dependency

            task = drain_outbox_batch
        task.apply_async()
    except Exception:  # pragma: no cover - defensive
        log.exception("outbox_drain_schedule_failed")
