from django.utils import timezone
from .models import Lead, LeadEvent
from .audit import log_enrich, log_route
from apps.catalog.models.models import Course
from apps.billing.services import PaymentService, PriceService  # existants chez toi

class EnrichmentService:
    @staticmethod
    def normalize(lead: Lead):
        # Normalisations légères (exemples)
        lead.email = (lead.email or "").strip().lower()
        lead.phone = (lead.phone or "").strip()
        lead.full_name = (lead.full_name or "").strip()
        # Consentement horodaté
        if lead.consent and not lead.consent_at:
            lead.consent_at = timezone.now()
        lead.save(update_fields=[
            "email", "phone", "full_name", "consent_at", "updated_at"
        ])
        LeadEvent.objects.create(lead=lead, event="normalized", payload={})
        log_enrich.info("lead_normalized lead=%s", lead.id)

class ScoringService:
    @staticmethod
    def score(lead: Lead) -> float:
        score = 0.0
        if lead.email:
            score += 10
        if lead.phone:
            score += 5
        if lead.form_kind == "checkout_intent":
            score += 20
        return score

class RoutingService:
    @staticmethod
    def after_validation(lead: Lead):
        # email_ebook : ici, brancher un envoi d’email / newsletter si besoin
        if lead.form_kind == "email_ebook":
            LeadEvent.objects.create(lead=lead, event="ebook_optin", payload={"ebook_id": lead.ebook_id})
            log_route.info("lead_ebook_optin lead=%s ebook=%s", lead.id, lead.ebook_id)
            return

        # contact_full : notif interne/CRM (placeholder)
        if lead.form_kind == "contact_full":
            LeadEvent.objects.create(lead=lead, event="crm_queue", payload={})
            log_route.info("lead_contact_crm lead=%s", lead.id)
            return

        # checkout_intent : pré-provision Order + PaymentIntent (comme ton billing)
        if lead.form_kind == "checkout_intent" and lead.course_slug and lead.email:
            try:
                course = Course.objects.published().get(slug=lead.course_slug)
            except Course.DoesNotExist:
                return
            currency = lead.currency or "EUR"
            # Pas d'user (lead anonyme) => user=None
            order, payload = PaymentService.create_or_update_order_and_intent(
                user=None,
                email=lead.email,
                course=course,
                currency=PriceService.select_currency(currency),
            )
            lead.order_id = order.id
            lead.save(update_fields=["order", "updated_at"])
            LeadEvent.objects.create(lead=lead, event="order_preprovisioned",
                                     payload={"order_id": order.id, "client_secret": payload.get("client_secret")})
            log_route.info("lead_checkout_order lead=%s order=%s", lead.id, order.id)