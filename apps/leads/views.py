import hashlib, json

from django.db import IntegrityError
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .permissions import PublicPOSTOnly
from .serializers import DynamicLeadSerializer
from .models import Lead, LeadEvent
from .constants import LeadStatus, RejectReason
from .audit import log_api, log_antispam
from .conf import get_global_policy
import logging

from .antispam import idempotency_seen, verify_signed_token, normalize_email
from .tasks import process_lead


logger = logging.getLogger(__name__)
# Toutes les clefs participent à la signature pour éviter les falsifications sur le payload.
IGNORE_SIGNATURE_FIELDS: set[str] = set()

# --- SIGN ENDPOINT (génère un signed_token pour /leads/collect) ---
import time, hmac, hashlib, json
from django.conf import settings
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

        # ne jamais signer un champ déjà présent
        payload_wo = {k: v for k, v in payload.items() if k != "signed_token"}

        # md5(JSON trié) exactement comme côté collect/verify
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

    def post(self, request, *args, **kwargs):
        payload = request.data or {}
        log_api.info("collect_request kind=%s ua=%s ip=%s",payload.get("form_kind"), request.META.get("HTTP_USER_AGENT"), request.META.get("REMOTE_ADDR"))
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
        if global_pol.get("signed_token_required", True):
            stoken = payload.get("signed_token")
            msg_body = dict(payload)
            msg_body.pop("signed_token", None)
            strict_hash = hashlib.md5(json.dumps(msg_body, sort_keys=True).encode()).hexdigest()
            if not verify_signed_token(stoken, strict_hash, max_age_s=int(global_pol.get("client_ts_max_skew_seconds", 7200))):
                tolerant_body = {k: v for k, v in msg_body.items() if k not in IGNORE_SIGNATURE_FIELDS}
                tolerant_hash = hashlib.md5(json.dumps(tolerant_body, sort_keys=True).encode()).hexdigest()
                if not verify_signed_token(stoken, tolerant_hash, max_age_s=int(global_pol.get("client_ts_max_skew_seconds", 7200))):
                    logger.info("signature mismatch", extra={"fields": sorted(msg_body.keys())})
                    self._audit(request, payload, 0, RejectReason.ANTIFORGERY)
                    return Response({"detail": "Token invalide."}, status=status.HTTP_400_BAD_REQUEST)

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


        context_payload = data.get("context") if isinstance(data.get("context"), dict) else {}
        context_payload = dict(context_payload)
        attribution_cookie = getattr(request, "_attribution", {}) or {}
        if attribution_cookie:
            context_payload["ads_attribution"] = attribution_cookie

        try:
            # Crée le lead minimal
            lead = Lead.objects.create(
                form_kind=data.get("form_kind"),
                campaign=data.get("campaign") or "",
                source=data.get("source") or "",
                utm_source=data.get("utm_source") or "",
                utm_medium=data.get("utm_medium") or "",
                utm_campaign=data.get("utm_campaign") or "",
                context=context_payload,
                email=normalize_email(data.get("email")),
                first_name=data.get("first_name") or "",
                last_name=data.get("last_name") or "",
                full_name=data.get("full_name") or "",
                phone=data.get("phone") or "",
                address_line1=data.get("address_line1") or "",
                address_line2=data.get("address_line2") or "",
                city=data.get("city") or "",
                state=data.get("state") or "",
                postal_code=data.get("postal_code") or "",
                country=data.get("country") or "",
                course_slug=data.get("course_slug") or "",
                currency=(data.get("currency") or "").upper(),
                coupon_code=data.get("coupon_code") or "",
                billing_address_line1=data.get("billing_address_line1") or "",
                billing_address_line2=data.get("billing_address_line2") or "",
                billing_city=data.get("billing_city") or "",
                billing_state=data.get("billing_state") or "",
                billing_postal_code=data.get("billing_postal_code") or "",
                billing_country=(data.get("billing_country") or "").upper(),
                company_name=data.get("company_name") or "",
                tax_id_type=data.get("tax_id_type") or "",
                tax_id=data.get("tax_id") or "",
                save_customer=bool(data.get("save_customer") or False),
                accept_terms=bool(data.get("accept_terms") or False),
                invoice_language=data.get("invoice_language") or "",
                ebook_id=data.get("ebook_id") or "",
                newsletter_optin=bool(data.get("newsletter_optin") or False),
                consent=bool(data.get("consent") or False),
                consent_ip=request.META.get("REMOTE_ADDR"),
                consent_user_agent=request.META.get("HTTP_USER_AGENT", "")[:300],
                idempotency_key=idem_key or "",
                client_ts=data.get("client_ts"),
                signed_token_hash="",  # utile si tu veux historiser le token
                honeypot_value=payload.get("honeypot") or "",
                status=LeadStatus.PENDING,
                ip_addr=request.META.get("REMOTE_ADDR"),
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:300],
                referer=request.META.get("HTTP_REFERER", "")[:500],
                page_path=request.META.get("REQUEST_URI", "")[:300],
                locale=(request.headers.get("Accept-Language") or "")[:16],
                ab_variant=(payload.get("ab_variant") or "")[:32],
            )

        except IntegrityError:
            # If a concurrent/previous request inserted the same idempotency_key, treat as duplicate (202).
            return Response({"status": "duplicate", "detail": "déjà reçu"}, status=status.HTTP_202_ACCEPTED)

        LeadEvent.objects.create(lead=lead, event="accepted", payload={})
        log_api.info("lead_accepted lead=%s kind=%s", lead.id, lead.form_kind)

        # Enfile le traitement
        process_lead.delay(lead.id)

        return Response({"status": "pending", "lead_id": lead.id, "detail": "queued"}, status=status.HTTP_202_ACCEPTED)

    def _audit(self, request, payload, lead_id, reason: str, errors=None):
        log_antispam.info("lead_rejected reason=%s ip=%s ua=%s", reason, request.META.get("REMOTE_ADDR"), request.META.get("HTTP_USER_AGENT"))
