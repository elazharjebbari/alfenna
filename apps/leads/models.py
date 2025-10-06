from django.db import models
from django.utils import timezone
from .constants import FormKind, LeadStatus


class Lead(models.Model):
    form_kind = models.CharField(max_length=32, choices=FormKind.choices)
    campaign = models.CharField(max_length=64, blank=True, default="")
    source = models.CharField(max_length=64, blank=True, default="")
    utm_source = models.CharField(max_length=64, blank=True, default="")
    utm_medium = models.CharField(max_length=64, blank=True, default="")
    utm_campaign = models.CharField(max_length=64, blank=True, default="")
    context = models.JSONField(default=dict, blank=True)

    # identité & contact
    email = models.EmailField(blank=True, default="")
    first_name = models.CharField(max_length=100, blank=True, default="")
    last_name = models.CharField(max_length=100, blank=True, default="")
    full_name = models.CharField(max_length=150, blank=True, default="")
    phone = models.CharField(max_length=32, blank=True, default="")

    # adresse
    address_line1 = models.CharField(max_length=200, blank=True, default="")
    address_line2 = models.CharField(max_length=200, blank=True, default="")
    city = models.CharField(max_length=100, blank=True, default="")
    state = models.CharField(max_length=100, blank=True, default="")
    postal_code = models.CharField(max_length=20, blank=True, default="")
    country = models.CharField(max_length=2, blank=True, default="")

    # produit / checkout intent
    course_slug = models.SlugField(max_length=220, blank=True, default="")
    currency = models.CharField(max_length=3, blank=True, default="")
    coupon_code = models.CharField(max_length=64, blank=True, default="")
    billing_address_line1 = models.CharField(max_length=200, blank=True, default="")
    billing_address_line2 = models.CharField(max_length=200, blank=True, default="")
    billing_city = models.CharField(max_length=100, blank=True, default="")
    billing_state = models.CharField(max_length=100, blank=True, default="")
    billing_postal_code = models.CharField(max_length=20, blank=True, default="")
    billing_country = models.CharField(max_length=2, blank=True, default="")
    company_name = models.CharField(max_length=150, blank=True, default="")
    tax_id_type = models.CharField(max_length=16, blank=True, default="")
    tax_id = models.CharField(max_length=32, blank=True, default="")
    save_customer = models.BooleanField(default=False)
    accept_terms = models.BooleanField(default=False)
    invoice_language = models.CharField(max_length=8, blank=True, default="")

    # spécifique ebook
    ebook_id = models.CharField(max_length=64, blank=True, default="")
    newsletter_optin = models.BooleanField(default=False)

    # consentement + traces sécurité
    consent = models.BooleanField(default=False)
    consent_at = models.DateTimeField(null=True, blank=True)
    consent_ip = models.GenericIPAddressField(null=True, blank=True)
    consent_user_agent = models.CharField(max_length=300, blank=True, default="")

    idempotency_key = models.CharField(max_length=200, unique=True)
    client_ts = models.DateTimeField(null=True, blank=True)
    signed_token_hash = models.CharField(max_length=64, blank=True, default="")
    honeypot_value = models.CharField(max_length=200, blank=True, default="")

    # état & enrichissement
    status = models.CharField(max_length=16, choices=LeadStatus.choices, default=LeadStatus.PENDING)
    reject_reason = models.CharField(max_length=32, blank=True, default="")
    score = models.FloatField(default=0.0)
    risk_flags = models.JSONField(default=dict, blank=True)
    enriched_at = models.DateTimeField(null=True, blank=True)

    # observabilité
    ip_addr = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True, default="")
    referer = models.CharField(max_length=500, blank=True, default="")
    page_path = models.CharField(max_length=300, blank=True, default="")
    locale = models.CharField(max_length=16, blank=True, default="")
    ab_variant = models.CharField(max_length=32, blank=True, default="")

    # liens
    duplicate_of_lead = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL,
                                          related_name="duplicates")
    order = models.ForeignKey("billing.Order", null=True, blank=True, on_delete=models.SET_NULL, related_name="leads")

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["form_kind", "email", "created_at"]),
            models.Index(fields=["status"]),
            models.Index(fields=["course_slug", "created_at"]),
        ]

    def __str__(self):
        return f"Lead#{self.id} {self.form_kind} {self.email or self.phone}"


class LeadEvent(models.Model):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="events")
    event = models.CharField(max_length=50)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]




# ⬇️ Journal de soumission, statuts réutilisent LeadStatus (PENDING/VALID/REJECTED/FAILED_TEMP)
class LeadSubmissionLog(models.Model):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="submissions")
    flow_key = models.CharField(max_length=64)
    session_key = models.CharField(max_length=64, blank=True, default="")
    status = models.CharField(max_length=16, choices=LeadStatus.choices, default=LeadStatus.PENDING)
    message = models.CharField(max_length=500, blank=True, default="")
    payload = models.JSONField(default=dict, blank=True)  # snapshot au moment de la soumission
    attempt_count = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["lead", "flow_key", "created_at"]),
            models.Index(fields=["status"]),
        ]
        unique_together = (("lead", "flow_key", "session_key"),)

    def __str__(self):
        return f"LeadSubmissionLog(lead={self.lead_id}, flow={self.flow_key}, sess={self.session_key}, status={self.status})"