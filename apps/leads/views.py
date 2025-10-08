import hashlib, json
import logging
from datetime import date, datetime
from typing import Any, Iterable

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.flowforms.models import FlowSession, FlowStatus

from .antispam import idempotency_seen, normalize_email, verify_signed_token
from .audit import log_api, log_antispam
from .conf import get_global_policy
from .constants import FormKind, LeadStatus, RejectReason
from .models import Lead, LeadEvent, LeadSubmissionLog
from .permissions import PublicPOSTOnly
from .serializers import DynamicLeadSerializer
from .tasks import process_lead


logger = logging.getLogger(__name__)
DEFAULT_SIGNATURE_IGNORED_KEYS: set[str] = {"context", "consent"}


def _signature_ignore_keys(extra: Iterable[str] | None = None) -> set[str]:
    base = set(DEFAULT_SIGNATURE_IGNORED_KEYS)
    base.update(_configured_signature_ignores())
    if extra:
        base.update(extra)
    return base


def _canonical_payload(payload: dict[str, Any], *, extra_ignore: Iterable[str] | None = None) -> dict[str, Any]:
    ignore = _signature_ignore_keys(extra_ignore)
    return {k: v for k, v in payload.items() if k not in ignore and k != "signed_token"}


def _payload_hash(payload: dict[str, Any], *, extra_ignore: Iterable[str] | None = None) -> str:
    canonical = _canonical_payload(payload, extra_ignore=extra_ignore)
    return hashlib.md5(json.dumps(canonical, sort_keys=True).encode("utf-8")).hexdigest()


def _configured_signature_ignores() -> set[str]:
    configured = getattr(settings, "LEADS_SIGNATURE_IGNORE_FIELDS", None)
    if not configured:
        return set()
    if isinstance(configured, (list, tuple, set)):
        return set(configured)
    return {str(configured)}


def _deep_merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = _deep_merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged

# --- SIGN ENDPOINT (génère un signed_token pour /leads/collect) ---
import time, hmac, hashlib, json
from django.http import JsonResponse
from rest_framework.views import APIView
from .permissions import PublicPOSTOnly

class SignPayloadView(APIView):
    """
    POST /api/leads/sign/
    Corps accepté:
      - soit {"payload": {...}}
      - soit directement {...} (le payload lui-même)

    Réponse: {"signed_token": "<ts>.<hmac>", "ts": <int>}
    """
    permission_classes = [PublicPOSTOnly]
    authentication_classes = []  # public
    throttle_classes = []        # à ajouter si besoin

    def post(self, request, *args, **kwargs):
        # DRF → request.data est déjà du JSON parsé
        incoming = request.data if isinstance(request.data, dict) else {}
        payload = incoming.get("payload", incoming)

        if not isinstance(payload, dict) or not payload:
            return JsonResponse({"detail": "payload invalide"}, status=400)

        payload_wo = _canonical_payload(payload)
        try:
            msg = hashlib.md5(
                json.dumps(payload_wo, sort_keys=True).encode("utf-8")
            ).hexdigest()
        except Exception:
            return JsonResponse({"detail": "payload non sérialisable"}, status=400)

        ts = int(time.time())
        secret = getattr(settings, "LEADS_SIGNING_SECRET", settings.SECRET_KEY)
        mac = hmac.new(secret.encode("utf-8"), f"{ts}.{msg}".encode("utf-8"), hashlib.sha256).hexdigest()
        token = f"{ts}.{mac}"

        return JsonResponse({"signed_token": token, "ts": ts}, status=200)


class LeadCollectAPIView(APIView):
    permission_classes = [PublicPOSTOnly]
    authentication_classes = []  # public
    throttle_scope = None  # on utilise nos classes custom via settings

    @staticmethod
    def _build_context(data: dict[str, Any], request) -> dict[str, Any]:
        ctx = data.get("context") if isinstance(data.get("context"), dict) else {}
        ctx = dict(ctx)
        attribution_cookie = getattr(request, "_attribution", {}) or {}
        if attribution_cookie:
            ctx["ads_attribution"] = attribution_cookie
        return ctx

    @classmethod
    def _build_lead_values(
        cls,
        data: dict[str, Any],
        request,
        idem_key: str,
        raw_payload: dict[str, Any],
    ) -> dict[str, Any]:
        context_payload = cls._build_context(data, request)
        return {
            "form_kind": data.get("form_kind"),
            "campaign": data.get("campaign") or "",
            "source": data.get("source") or "",
            "utm_source": data.get("utm_source") or "",
            "utm_medium": data.get("utm_medium") or "",
            "utm_campaign": data.get("utm_campaign") or "",
            "context": context_payload,
            "email": normalize_email(data.get("email")),
            "first_name": data.get("first_name") or "",
            "last_name": data.get("last_name") or "",
            "full_name": data.get("full_name") or "",
            "phone": data.get("phone") or "",
            "address_line1": data.get("address_line1") or "",
            "address_line2": data.get("address_line2") or "",
            "city": data.get("city") or "",
            "state": data.get("state") or "",
            "postal_code": data.get("postal_code") or "",
            "country": data.get("country") or "",
            "course_slug": data.get("course_slug") or "",
            "currency": (data.get("currency") or "").upper(),
            "coupon_code": data.get("coupon_code") or "",
            "billing_address_line1": data.get("billing_address_line1") or "",
            "billing_address_line2": data.get("billing_address_line2") or "",
            "billing_city": data.get("billing_city") or "",
            "billing_state": data.get("billing_state") or "",
            "billing_postal_code": data.get("billing_postal_code") or "",
            "billing_country": (data.get("billing_country") or "").upper(),
            "company_name": data.get("company_name") or "",
            "tax_id_type": data.get("tax_id_type") or "",
            "tax_id": data.get("tax_id") or "",
            "save_customer": bool(data.get("save_customer") or False),
            "accept_terms": bool(data.get("accept_terms") or False),
            "invoice_language": data.get("invoice_language") or "",
            "ebook_id": data.get("ebook_id") or "",
            "newsletter_optin": bool(data.get("newsletter_optin") or False),
            "consent": bool(data.get("consent") or False),
            "consent_ip": request.META.get("REMOTE_ADDR"),
            "consent_user_agent": request.META.get("HTTP_USER_AGENT", "")[:300],
            "idempotency_key": idem_key or "",
            "client_ts": data.get("client_ts"),
            "signed_token_hash": "",
            "honeypot_value": raw_payload.get("honeypot") or "",
            "status": LeadStatus.PENDING,
            "ip_addr": request.META.get("REMOTE_ADDR"),
            "user_agent": request.META.get("HTTP_USER_AGENT", "")[:300],
            "referer": request.META.get("HTTP_REFERER", "")[:500],
            "page_path": request.META.get("REQUEST_URI", "")[:300],
            "locale": (request.headers.get("Accept-Language") or "")[:16],
            "ab_variant": (raw_payload.get("ab_variant") or "")[:32],
        }

    @staticmethod
    def _assign_lead_fields(lead: Lead, values: dict[str, Any]) -> None:
        update_fields: list[str] = []
        for field, value in values.items():
            if field == "context":
                continue
            if getattr(lead, field) != value:
                setattr(lead, field, value)
                update_fields.append(field)

        context_payload = values.get("context")
        if isinstance(context_payload, dict):
            merged_context = dict(lead.context or {})
            merged_context.update(context_payload)
            if merged_context != (lead.context or {}):
                lead.context = merged_context
                update_fields.append("context")

        if update_fields:
            update_fields.append("updated_at")
            lead.save(update_fields=sorted(set(update_fields)))

    @staticmethod
    def _update_flowsession(flowsession: FlowSession | None, payload: dict[str, Any], lead: Lead | None) -> None:
        if not flowsession:
            return
        snapshot = dict(flowsession.data_snapshot or {})
        snapshot = _deep_merge_dict(snapshot, payload)
        flowsession.data_snapshot = snapshot
        flowsession.current_step = "collect"
        flowsession.status = FlowStatus.ACTIVE
        flowsession.last_touch_at = timezone.now()
        if lead:
            flowsession.lead = lead
        flowsession.save(
            update_fields=[
                "data_snapshot",
                "current_step",
                "status",
                "last_touch_at",
                "updated_at",
                "lead",
            ]
        )

    @staticmethod
    def _log_collect(lead: Lead | None, flowsession: FlowSession | None, payload: dict[str, Any]) -> None:
        if not lead or not flowsession:
            return
        sanitized = LeadCollectAPIView._json_safe_payload({k: v for k, v in payload.items() if k != "signed_token"})
        LeadSubmissionLog.objects.update_or_create(
            lead=lead,
            flow_key=flowsession.flow_key,
            session_key=flowsession.session_key,
            step="collect",
            defaults={
                "status": LeadStatus.PENDING,
                "message": "collect",
                "payload": sanitized,
            },
        )

    @staticmethod
    def _json_safe_payload(payload: dict[str, Any]) -> dict[str, Any]:
        def _convert(value: Any) -> Any:
            if isinstance(value, (datetime, date)):
                return value.isoformat()
            if isinstance(value, dict):
                return {k: _convert(v) for k, v in value.items()}
            if isinstance(value, list):
                return [_convert(v) for v in value]
            return value

        return _convert(payload)

    def post(self, request, *args, **kwargs):
        payload = dict(request.data or {})
        raw_payload = dict(payload)
        flow_key = str(payload.pop("ff_flow_key", payload.pop("ff_flow", "")) or "").strip()
        session_key = str(payload.pop("ff_session_key", payload.pop("flow_session_key", "")) or "").strip()

        log_api.info(
            "collect_request kind=%s ua=%s ip=%s",
            payload.get("form_kind"),
            request.META.get("HTTP_USER_AGENT"),
            request.META.get("REMOTE_ADDR"),
        )
        global_pol = get_global_policy()

        # Idempotency header
        idem_key = request.headers.get("X-Idempotency-Key", "")
        if global_pol.get("require_idempotency_header", True):
            if not idem_key:
                return Response({"detail": "X-Idempotency-Key requis."}, status=status.HTTP_400_BAD_REQUEST)

            # Short-circuit if a Lead with this idempotency_key already exists (DB-level idempotency)
            existing = Lead.objects.filter(idempotency_key=idem_key).only("id").first()
            if existing:
                return Response({"status": "duplicate", "detail": "déjà reçu"}, status=status.HTTP_202_ACCEPTED)

            # Cache-level idempotency (atomic)
            if idempotency_seen(payload.get("form_kind", ""), idem_key, ttl=3600):
                return Response({"status": "duplicate", "detail": "déjà reçu"}, status=status.HTTP_202_ACCEPTED)

        # CSRF/HMAC token (si cross-origin)
        # if global_pol.get("signed_token_required", False):
        #     stoken = payload.get("signed_token")
        #     msg_body = dict(payload)
        #     strict_hash = _payload_hash(msg_body)
        #     if not verify_signed_token(stoken, strict_hash, max_age_s=int(global_pol.get("client_ts_max_skew_seconds", 7200))):
        #         tolerant_extra = _configured_signature_ignores()
        #         tolerant_hash = _payload_hash(msg_body, extra_ignore=tolerant_extra)
        #         if not verify_signed_token(stoken, tolerant_hash, max_age_s=int(global_pol.get("client_ts_max_skew_seconds", 7200))):
        #             logger.info("signature mismatch", extra={"fields": sorted(msg_body.keys())})
        #             self._audit(request, payload, 0, RejectReason.ANTIFORGERY)
        #             return Response({"detail": "Token invalide."}, status=status.HTTP_400_BAD_REQUEST)

        # Honeypot
        if (payload.get("honeypot") or "").strip():
            self._audit(request, payload, 0, RejectReason.HONEYPOT)
            return Response({"detail": "Rejected."}, status=status.HTTP_202_ACCEPTED)

        # Serializer (politique dynamique)
        ser = DynamicLeadSerializer(data=payload)
        if not ser.is_valid():
            self._audit(request, payload, 0, RejectReason.INVALID, errors=ser.errors)
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

        data = ser.validated_data

        if not flow_key and data.get("form_kind") == FormKind.CHECKOUT_INTENT:
            flow_key = "checkout_intent_flow"

        snapshot_payload = self._json_safe_payload(dict(data))
        snapshot_payload.pop("signed_token", None)

        lead_values = self._build_lead_values(data, request, idem_key, raw_payload)

        flowsession: FlowSession | None = None
        lead: Lead | None = None

        with transaction.atomic():
            if flow_key and session_key:
                try:
                    flowsession = FlowSession.objects.select_for_update().get(
                        flow_key=flow_key,
                        session_key=session_key,
                    )
                except FlowSession.DoesNotExist:
                    flowsession = FlowSession.objects.create(
                        flow_key=flow_key,
                        session_key=session_key,
                        status=FlowStatus.ACTIVE,
                        data_snapshot={},
                    )

                if flowsession.lead_id:
                    try:
                        lead = Lead.objects.select_for_update().get(id=flowsession.lead_id)
                    except Lead.DoesNotExist:
                        lead = None

            if lead:
                self._assign_lead_fields(lead, lead_values)
            else:
                try:
                    lead = Lead.objects.create(**lead_values)
                except IntegrityError:
                    return Response({"status": "duplicate", "detail": "déjà reçu"}, status=status.HTTP_202_ACCEPTED)

            if flowsession and flowsession.lead_id != lead.id:
                flowsession.lead = lead
                flowsession.save(update_fields=["lead", "updated_at"])

            self._update_flowsession(flowsession, snapshot_payload, lead)
            self._log_collect(lead, flowsession, snapshot_payload)

        LeadEvent.objects.create(lead=lead, event="accepted", payload={})
        log_api.info("lead_accepted lead=%s kind=%s", lead.id, lead.form_kind)

        process_lead.delay(lead.id)

        return Response({"status": "pending", "lead_id": lead.id, "detail": "queued"}, status=status.HTTP_202_ACCEPTED)

    def _audit(self, request, payload, lead_id, reason: str, errors=None):
        log_antispam.info("lead_rejected reason=%s ip=%s ua=%s", reason, request.META.get("REMOTE_ADDR"), request.META.get("HTTP_USER_AGENT"))
