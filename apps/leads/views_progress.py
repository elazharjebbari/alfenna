from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

import logging

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.flowforms.models import FlowSession, FlowStatus

from .antispam import normalize_email
from .audit import log_api, log_submit
from .constants import FormKind, LeadStatus
from .models import Lead, LeadSubmissionLog
from .permissions import PublicPOSTOnly


logger = logging.getLogger("leads.progress")


_LEAD_UPDATABLE_FIELDS: tuple[str, ...] = (
    "full_name",
    "first_name",
    "last_name",
    "email",
    "phone",
    "address_line1",
    "address_line2",
    "city",
    "state",
    "postal_code",
    "country",
    "billing_address_line1",
    "billing_address_line2",
    "billing_city",
    "billing_state",
    "billing_postal_code",
    "billing_country",
    "company_name",
    "tax_id_type",
    "tax_id",
    "course_slug",
    "currency",
    "coupon_code",
    "client_ts",
    "locale",
    "ab_variant",
    "newsletter_optin",
    "consent",
)

_CONTEXT_ENRICH_KEYS: tuple[str, ...] = (
    "product",
    "offer_key",
    "quantity",
    "bump_optin",
    "promotion_selected",
    "payment_method",
    "address_raw",
    "wa_optin",
)


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _make_idempotency_key(flow_key: str, session_key: str) -> str:
    return f"flow:{flow_key}:{session_key}"


def _normalise_email(value: Any) -> str:
    if not value:
        return ""
    return normalize_email(str(value))


def _coerce_boolean(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on", "y"}:
            return True
        if lowered in {"0", "false", "no", "off", "n"}:
            return False
    return bool(value)


@dataclass(slots=True)
class ProgressResult:
    lead: Lead
    flowsession: FlowSession
    snapshot: Dict[str, Any]
    step_payload: Dict[str, Any]
    step: str


class LeadProgressSerializer(serializers.Serializer):
    flow_key = serializers.CharField(max_length=64)
    session_key = serializers.CharField(max_length=64)
    step = serializers.CharField(max_length=64)
    payload = serializers.DictField(child=serializers.JSONField(), required=False)
    form_kind = serializers.CharField(max_length=32, required=False)

    def validate_form_kind(self, value: str) -> str:
        return value or FormKind.CHECKOUT_INTENT


class LeadProgressAPIView(APIView):
    permission_classes = [PublicPOSTOnly]
    authentication_classes: list[Any] = []
    throttle_scope = None

    def post(self, request, *args, **kwargs):
        serializer = LeadProgressSerializer(data=request.data)
        if not serializer.is_valid():
            log_api.info(
                "progress_invalid flow=%s session=%s",
                request.data.get("flow_key"),
                request.data.get("session_key"),
            )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        step_payload = data.get("payload") or {}

        log_api.info(
            "progress_request flow=%s session=%s step=%s",
            data["flow_key"],
            data["session_key"],
            data["step"],
        )

        try:
            result = self._persist_progress(
                flow_key=data["flow_key"],
                session_key=data["session_key"],
                form_kind=data["form_kind"],
                step=data["step"],
                step_payload=step_payload,
                meta={
                    "user_agent": request.META.get("HTTP_USER_AGENT", "")[:300],
                    "ip": request.META.get("REMOTE_ADDR"),
                },
            )
        except ValueError as exc:
            log_submit.warning(
                "progress_rejected flow=%s session=%s step=%s reason=%s",
                data["flow_key"],
                data["session_key"],
                data["step"],
                exc,
            )
            log_api.info(
                "progress_conflict flow=%s session=%s step=%s",
                data["flow_key"],
                data["session_key"],
                data["step"],
            )
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except Exception:
            logger.exception(
                "progress_exception flow=%s session=%s step=%s",
                data["flow_key"],
                data["session_key"],
                data["step"],
            )
            log_api.info(
                "progress_error flow=%s session=%s step=%s",
                data["flow_key"],
                data["session_key"],
                data["step"],
            )
            return Response({"detail": "progress_failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        log_submit.info(
            "progress_ok lead=%s flow=%s session=%s step=%s",
            result.lead.id,
            result.flowsession.flow_key,
            result.flowsession.session_key,
            result.step,
        )
        log_api.info(
            "progress_ok flow=%s session=%s step=%s lead=%s",
            result.flowsession.flow_key,
            result.flowsession.session_key,
            result.step,
            result.lead.id,
        )

        return Response(
            {
                "lead_id": result.lead.id,
                "flowsession_id": result.flowsession.id,
                "step": result.step,
                "session_key": result.flowsession.session_key,
                "snapshot": result.snapshot,
            },
            status=status.HTTP_200_OK,
        )

    def _persist_progress(
        self,
        *,
        flow_key: str,
        session_key: str,
        form_kind: str,
        step: str,
        step_payload: Dict[str, Any],
        meta: Dict[str, Any],
    ) -> ProgressResult:
        if not step:
            raise ValueError("step_missing")

        with transaction.atomic():
            fs, created = self._get_or_create_session(flow_key, session_key)

            lead = fs.lead or self._ensure_lead(fs, form_kind, created)
            self._apply_lead_updates(lead, step_payload, meta)

            snapshot_before = dict(fs.data_snapshot or {})
            snapshot_after = _deep_merge(snapshot_before, step_payload)

            fs.current_step = step
            fs.data_snapshot = snapshot_after
            fs.status = FlowStatus.ACTIVE
            fs.last_touch_at = timezone.now()
            fs.lead = lead
            fs.save(
                update_fields=[
                    "current_step",
                    "data_snapshot",
                    "status",
                    "last_touch_at",
                    "updated_at",
                    "lead",
                ]
            )

            self._log_progress(lead, fs, step, step_payload)

        return ProgressResult(
            lead=lead,
            flowsession=fs,
            snapshot=snapshot_after,
            step_payload=step_payload,
            step=step,
        )

    def _get_or_create_session(self, flow_key: str, session_key: str) -> tuple[FlowSession, bool]:
        try:
            fs = (
                FlowSession.objects.select_for_update()
                .get(flow_key=flow_key, session_key=session_key)
            )
            return fs, False
        except FlowSession.DoesNotExist:
            fs = FlowSession.objects.create(
                flow_key=flow_key,
                session_key=session_key,
                status=FlowStatus.ACTIVE,
                data_snapshot={},
            )
            return fs, True

    def _ensure_lead(self, fs: FlowSession, form_kind: str, session_created: bool) -> Lead:
        if fs.lead:
            return fs.lead

        if form_kind != FormKind.CHECKOUT_INTENT:
            # fallback sur un lead minimal pour autres formulaires si besoin
            form_kind_value = form_kind
        else:
            form_kind_value = FormKind.CHECKOUT_INTENT

        lead, created = Lead.objects.get_or_create(
            idempotency_key=_make_idempotency_key(fs.flow_key, fs.session_key),
            defaults={
                "form_kind": form_kind_value,
                "status": LeadStatus.PENDING,
            },
        )
        if not created and not lead.form_kind:
            lead.form_kind = form_kind_value
            lead.save(update_fields=["form_kind", "updated_at"])

        fs.lead = lead
        if session_created:
            fs.save(update_fields=["lead", "updated_at"])
        return lead

    def _apply_lead_updates(
        self,
        lead: Lead,
        payload: Dict[str, Any],
        meta: Dict[str, Any],
    ) -> None:
        dirty_fields: list[str] = []
        context_patch = {}

        for field in _LEAD_UPDATABLE_FIELDS:
            if field not in payload:
                continue
            value = payload[field]
            if isinstance(value, str):
                value = value.strip()
            if field == "email":
                value = _normalise_email(value)
            elif field in {"consent", "newsletter_optin"}:
                value = _coerce_boolean(value)
            elif field == "currency" and isinstance(value, str):
                value = value.upper()
            elif field in {"billing_country", "country"} and isinstance(value, str):
                value = value.upper()
            if getattr(lead, field) != value:
                setattr(lead, field, value)
                dirty_fields.append(field)

        for ctx_field in _CONTEXT_ENRICH_KEYS:
            if ctx_field in payload:
                context_patch[ctx_field] = payload[ctx_field]

        if context_patch:
            context = dict(lead.context or {})
            context.update(context_patch)
            lead.context = context
            dirty_fields.append("context")

        # trace meta si disponible (IP/UA sur premier passage typiquement)
        if meta.get("ip") and not lead.ip_addr:
            lead.ip_addr = meta["ip"]
            dirty_fields.append("ip_addr")
        if meta.get("user_agent") and not lead.user_agent:
            lead.user_agent = meta["user_agent"]
            dirty_fields.append("user_agent")

        if dirty_fields:
            # status reste PENDING tant que collect non soumis
            if "status" not in dirty_fields and lead.status != LeadStatus.PENDING:
                lead.status = LeadStatus.PENDING
                dirty_fields.append("status")
            lead.save(update_fields=sorted(set(dirty_fields + ["updated_at"])))

    def _log_progress(
        self,
        lead: Lead,
        fs: FlowSession,
        step: str,
        payload: Dict[str, Any],
    ) -> None:
        log, created = LeadSubmissionLog.objects.get_or_create(
            lead=lead,
            flow_key=fs.flow_key,
            session_key=fs.session_key,
            step=step,
            defaults={
                "status": LeadStatus.PENDING,
                "message": f"progress:{step}",
                "payload": payload,
            },
        )

        if not created:
            log.payload = payload
            log.message = f"progress:{step}"
            log.status = LeadStatus.PENDING
            log.save(update_fields=["payload", "message", "status", "updated_at"])
