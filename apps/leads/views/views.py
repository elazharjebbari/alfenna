import hashlib, json
import logging
from datetime import date, datetime
from typing import Any, Iterable

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.flowforms.models import FlowSession, FlowStatus

from apps.leads.antispam import idempotency_seen, normalize_email, verify_signed_token
from apps.leads.audit import log_api, log_antispam
from apps.leads.conf import get_global_policy
from apps.leads.constants import FormKind, LeadStatus, RejectReason
from apps.leads.models import Lead, LeadEvent, LeadSubmissionLog
from apps.leads.permissions import PublicPOSTOnly
from apps.leads.serializers import DynamicLeadSerializer
from apps.leads.tasks import process_lead
from apps.leads.submissions import merge_context_path


logger = logging.getLogger(__name__)
DEFAULT_SIGNATURE_IGNORED_KEYS: set[str] = {"context", "consent"}
LEAD_FIELD_NAMES = {f.name for f in Lead._meta.concrete_fields}


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


def _normalise_complementary_slugs(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return []
        if candidate.startswith("["):
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, list):
                    return [str(item) for item in parsed if str(item).strip()]
            except json.JSONDecodeError:
                pass
        return [candidate]
    return []

# --- SIGN ENDPOINT (génère un signed_token pour /leads/collect) ---
import time, hmac, hashlib, json
from django.http import JsonResponse
from rest_framework.views import APIView
from apps.leads.permissions import PublicPOSTOnly

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
    ) -> tuple[dict[str, Any], set[str]]:
        context_payload = cls._build_context(data, request)
        present_keys: set[str] = set()
        values: dict[str, Any] = {
            "form_kind": data.get("form_kind"),
            "context": context_payload,
            "idempotency_key": idem_key or "",
            "status": LeadStatus.PENDING,
            "consent_ip": request.META.get("REMOTE_ADDR"),
            "consent_user_agent": request.META.get("HTTP_USER_AGENT", "")[:300],
            "honeypot_value": raw_payload.get("honeypot") or "",
            "ip_addr": request.META.get("REMOTE_ADDR"),
            "user_agent": request.META.get("HTTP_USER_AGENT", "")[:300],
            "referer": request.META.get("HTTP_REFERER", "")[:500],
            "page_path": request.META.get("REQUEST_URI", "")[:300],
            "locale": (request.headers.get("Accept-Language") or "")[:16],
            "ab_variant": (raw_payload.get("ab_variant") or "")[:32],
            "signed_token_hash": "",
        }
        present_keys.update(values.keys())

        def set_value(key: str, value: Any) -> None:
            values[key] = value
            present_keys.add(key)

        def maybe_set(key: str, *, source: str | None = None, transform=None, uppercase: bool = False) -> None:
            src = source or key
            if src not in data:
                return
            value = data[src]
            if transform:
                value = transform(value)
            if uppercase and isinstance(value, str):
                value = value.upper()
            set_value(key, value)

        # marketing context (replay only if fourni)
        for marketing_key in ("campaign", "source", "utm_source", "utm_medium", "utm_campaign"):
            if marketing_key in data:
                set_value(marketing_key, data[marketing_key])

        maybe_set("email", transform=normalize_email)
        maybe_set("first_name")
        maybe_set("last_name")
        maybe_set("full_name")
        maybe_set("phone")
        maybe_set("address_line1")
        maybe_set("address_line2")
        maybe_set("city")
        maybe_set("state")
        maybe_set("postal_code")
        maybe_set("country", uppercase=True)
        maybe_set("pack_slug")
        maybe_set("currency", uppercase=True)
        maybe_set("coupon_code")
        maybe_set("billing_address_line1")
        maybe_set("billing_address_line2")
        maybe_set("billing_city")
        maybe_set("billing_state")
        maybe_set("billing_postal_code")
        maybe_set("billing_country", uppercase=True)
        maybe_set("company_name")
        maybe_set("tax_id_type")
        maybe_set("tax_id")
        maybe_set("product")
        maybe_set("offer_key")
        maybe_set("quantity")
        maybe_set("payment_method")
        maybe_set("payment_mode")
        maybe_set("wa_optin")
        maybe_set("bump_optin")
        maybe_set("promotion_selected")
        maybe_set("address_raw")
        maybe_set("ebook_id")
        maybe_set("client_ts")

        if "save_customer" in data:
            set_value("save_customer", bool(data.get("save_customer")))
        if "accept_terms" in data:
            set_value("accept_terms", bool(data.get("accept_terms")))
        if "newsletter_optin" in data:
            set_value("newsletter_optin", bool(data.get("newsletter_optin")))
        if "consent" in data:
            set_value("consent", bool(data.get("consent")))
        if "invoice_language" in data:
            set_value("invoice_language", data.get("invoice_language") or "")

        # Normaliser les alias payment_mode/payment_method
        if "payment_mode" not in present_keys and values.get("payment_method"):
            set_value("payment_mode", values["payment_method"])
        if "payment_method" not in present_keys and values.get("payment_mode"):
            set_value("payment_method", values["payment_mode"])

        # Dotted context.* keys → context_payload
        for key, value in data.items():
            if isinstance(key, str) and key.startswith("context."):
                sub_key = key.split(".", 1)[1].strip()
                if not sub_key:
                    continue
                if sub_key == "complementary_slugs":
                    value = _normalise_complementary_slugs(value)
                merge_context_path(context_payload, sub_key, value)

        # Contexte direct du payload (dict complet)
        if isinstance(data.get("context"), dict):
            for k, v in data["context"].items():
                if context_payload.get(k) != v:
                    context_payload[k] = v

        pack_value = (values.get("pack_slug") or "").strip()
        if not pack_value:
            pack_ctx = context_payload.get("pack")
            if isinstance(pack_ctx, dict) and pack_ctx.get("slug"):
                set_value("pack_slug", pack_ctx.get("slug"))

        values["context"] = context_payload

        allowed = set(LEAD_FIELD_NAMES) | {"context"}
        for key in list(values.keys()):
            if key not in allowed:
                values.pop(key, None)
                present_keys.discard(key)

        return values, present_keys

    @staticmethod
    def _assign_lead_fields(lead: Lead, values: dict[str, Any], present_keys: set[str]) -> None:
        update_fields: list[str] = []
        for field, value in values.items():
            if field == "context":
                continue
            if field not in present_keys:
                continue
            if not hasattr(lead, field):
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
    def _normalise_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
        normalised = dict(payload)
        if "context.complementary_slugs" in normalised:
            normalised["context.complementary_slugs"] = _normalise_complementary_slugs(
                normalised["context.complementary_slugs"]
            )
        return normalised

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

        # Alias legacy → champs requis par la politique
        if payload.get("payment_method") and not payload.get("payment_mode"):
            payload["payment_mode"] = payload.get("payment_method")
        if not payload.get("pack_slug"):
            pack_candidate = (
                payload.get("offer_key")
                or payload.get("offer")
                or payload.get("context.pack.slug")
            )
            if not pack_candidate:
                title = (
                    payload.get("context.pack.title")
                    or payload.get("offer_title")
                    or payload.get("pack_title")
                )
                if isinstance(title, str) and title.strip():
                    pack_candidate = slugify(title)
            if pack_candidate:
                payload["pack_slug"] = pack_candidate

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

        snapshot_payload = self._normalise_snapshot(self._json_safe_payload(dict(data)))
        snapshot_payload.pop("signed_token", None)

        lead_values, present_keys = self._build_lead_values(data, request, idem_key, raw_payload)

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
                self._assign_lead_fields(lead, lead_values, present_keys)
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
