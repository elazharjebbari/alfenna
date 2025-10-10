# apps/leads/views.py (ajout)
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from apps.leads.models import Lead, LeadStatus
from apps.leads.constants import FormKind


class LeadProgressAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        # 0) Idempotency (optionnel: court-circuit si doublon récent)
        idem = request.headers.get("X-Idempotency-Key") or ""
        if not idem:
            return Response({"errors": {"_": "Missing X-Idempotency-Key"}}, status=400)
        # if idempotency_seen(idem): return Response({"ok": True, "cached": True})

        payload = request.data or {}
        form_kind = payload.get("form_kind") or FormKind.CHECKOUT_INTENT
        ff_session_key = payload.get("ff_session_key") or request.session.session_key

        # 1) Champs connus tolérés pour la progression
        allowed = {
            # step1
            "full_name", "phone", "email",
            "address_line1", "address_line2", "city", "state", "postal_code", "country",
            # step2
            "offer_key", "pack_slug", "quantity", "context.complementary_slugs",
            # step3
            "payment_mode", "payment_method", "email", "currency", "accept_terms",
        }

        incoming = {k: v for k, v in payload.items()
                    if k in allowed or str(k).startswith("context.")}

        # 2) Retrouver/Créer le lead progressif
        # Politique: lookup par email ou phone si disponibles, sinon un PENDING vide
        lead = None
        email = incoming.get("email", "").strip().lower()
        phone = (incoming.get("phone") or "").strip()
        if email:
            lead = Lead.objects.filter(form_kind=form_kind, email__iexact=email).first()
        if not lead and phone:
            lead = Lead.objects.filter(form_kind=form_kind, phone=phone).first()
        if not lead:
            lead = Lead.objects.create(form_kind=form_kind, status=LeadStatus.PENDING)

        # 3) Merge tolérant
        ctx = dict(lead.context or {})
        for k, v in incoming.items():
            if str(k).startswith("context."):
                sub = k.split(".", 1)[1]
                # gérer liste vs scalaire
                if sub == "complementary_slugs":
                    if isinstance(v, list):
                        ctx["complementary_slugs"] = v
                    elif v:
                        ctx["complementary_slugs"] = [v]
                else:
                    ctx[sub] = v
            elif hasattr(lead, k):
                setattr(lead, k, v)
            else:
                # certains noms front (offer_key) peuvent aller en context
                ctx[k] = v

        lead.context = ctx
        lead.save(update_fields=[
            "email","phone","full_name","address_line1","address_line2",
            "city","state","postal_code","country","currency",
            "course_slug","coupon_code", "context",
            # + champ pack_slug si tu l’ajoutes au modèle (voir NOTE ci-dessous)
            "pack_slug",
        ])

        return Response({"ok": True, "lead_id": lead.id}, status=status.HTTP_200_OK)
