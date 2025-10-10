import logging
from typing import Dict

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.leads.constants import FormKind, LeadStatus
from apps.leads.models import Lead


logger = logging.getLogger("leads.progress")


class EchoHeadersAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        return Response({"headers": dict(request.headers)}, status=status.HTTP_200_OK)


class LeadProgressAPIView(APIView):
    permission_classes = [AllowAny]

    def _extract_incoming(self, payload: Dict[str, object]) -> Dict[str, object]:
        allowed = {
            # step1
            "full_name",
            "phone",
            "email",
            "address_line1",
            "address_line2",
            "city",
            "state",
            "postal_code",
            "country",
            # step2
            "offer_key",
            "offer",
            "pack_slug",
            "quantity",
            "context.complementary_slugs",
            "bump_optin",
            # step3
            "payment_mode",
            "payment_method",
            "currency",
            "accept_terms",
            "promotion_selected",
        }
        incoming = {
            key: value
            for key, value in payload.items()
            if key in allowed or str(key).startswith("context.")
        }
        nested_payload = payload.get("payload") if isinstance(payload, dict) else {}
        if isinstance(nested_payload, dict):
            for key, value in nested_payload.items():
                if key in allowed or str(key).startswith("context."):
                    incoming[key] = value
        return incoming

    def post(self, request, *args, **kwargs):
        logger.info("PROGRESS HEADERS: %s", dict(request.headers))
        logger.info(
            "PROGRESS META: %s",
            {k: v for k, v in request.META.items() if k.startswith("HTTP_")},
        )

        root_payload = request.data or {}
        idem = (
            request.headers.get("X-Idempotency-Key")
            or request.META.get("HTTP_X_IDEMPOTENCY_KEY")
            or root_payload.get("_idempotency_key")
            or root_payload.get("idempotency_key")
            or ""
        )
        if not idem:
            return Response({"errors": {"_": "Missing X-Idempotency-Key"}}, status=status.HTTP_400_BAD_REQUEST)

        form_kind = root_payload.get("form_kind") or FormKind.CHECKOUT_INTENT
        if form_kind != FormKind.CHECKOUT_INTENT:
            return Response({"errors": {"form_kind": "Unsupported"}}, status=status.HTTP_400_BAD_REQUEST)

        ff_session_key = (
            root_payload.get("ff_session_key")
            or root_payload.get("session_key")
            or request.session.session_key
        )

        nested_payload = root_payload.get("payload") if isinstance(root_payload, dict) else {}
        base_payload = dict(nested_payload if isinstance(nested_payload, dict) else root_payload)

        if "offer" in base_payload and not base_payload.get("offer_key"):
            base_payload["offer_key"] = base_payload["offer"]
        if "offer_key" in base_payload and not base_payload.get("offer"):
            base_payload["offer"] = base_payload["offer_key"]
        if "payment_method" in base_payload and not base_payload.get("payment_mode"):
            base_payload["payment_mode"] = base_payload["payment_method"]
        if "payment_mode" in base_payload and not base_payload.get("payment_method"):
            base_payload["payment_method"] = base_payload["payment_mode"]

        incoming = self._extract_incoming(base_payload)

        # Normalise compléments sous forme de liste
        comp_raw = incoming.get("context.complementary_slugs")
        if comp_raw is not None and not isinstance(comp_raw, list):
            if isinstance(comp_raw, str):
                if comp_raw.startswith("["):
                    try:
                        import json

                        incoming["context.complementary_slugs"] = json.loads(comp_raw)
                    except Exception:
                        incoming["context.complementary_slugs"] = [
                            slug for slug in comp_raw.split(",") if slug
                        ]
                else:
                    incoming["context.complementary_slugs"] = [
                        slug.strip() for slug in comp_raw.split(",") if slug.strip()
                    ]
            else:
                incoming["context.complementary_slugs"] = [comp_raw]

        def _first_val(value):
            if isinstance(value, list):
                for item in value:
                    if item not in (None, ""):
                        return item
                return ""
            return value

        lead = None
        email_raw = _first_val(incoming.get("email")) or ""
        phone_raw = _first_val(incoming.get("phone")) or ""
        email = str(email_raw).strip().lower()
        phone = str(phone_raw).strip()
        if email:
            lead = Lead.objects.filter(form_kind=form_kind, email__iexact=email).first()
        if not lead and phone:
            lead = Lead.objects.filter(form_kind=form_kind, phone=phone).first()
        if not lead and ff_session_key:
            lead = Lead.objects.filter(
                form_kind=form_kind,
                context__ff_session_key=ff_session_key,
            ).first()
        if not lead:
            lead = Lead.objects.create(
                form_kind=form_kind,
                status=LeadStatus.PENDING,
                idempotency_key=idem,
            )
        elif not getattr(lead, "idempotency_key", None):
            lead.idempotency_key = idem

        ctx = dict(lead.context or {})
        if ff_session_key:
            ctx.setdefault("ff_session_key", ff_session_key)
        for key, value in incoming.items():
            if str(key).startswith("context."):
                subkey = key.split(".", 1)[1]
                if subkey == "complementary_slugs":
                    ctx[subkey] = value if isinstance(value, list) else [value]
                else:
                    ctx[subkey] = value
            elif hasattr(lead, key):
                setattr(lead, key, value)
            else:
                if key == "quantity":
                    try:
                        ctx[key] = int(str(value).strip() or "1")
                    except Exception:
                        ctx[key] = 1
                else:
                    ctx[key] = value

        ctx.setdefault("idem_keys", [])
        if idem not in ctx["idem_keys"]:
            ctx["idem_keys"].append(idem)
        lead.context = ctx

        lead.save(
            update_fields=[
                "email",
                "phone",
                "full_name",
                "address_line1",
                "address_line2",
                "city",
                "state",
                "postal_code",
                "country",
                "currency",
                "course_slug",
                "coupon_code",
                "context",
                "pack_slug",
                "idempotency_key",
                "payment_mode",
            ]
        )

        return Response({"ok": True, "lead_id": lead.id}, status=status.HTTP_200_OK)
