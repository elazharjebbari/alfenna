from django.db import models

class FormKind(models.TextChoices):
    EMAIL_EBOOK = "email_ebook", "Email contre ebook"
    CONTACT_FULL = "contact_full", "Formulaire contact complet"
    CHECKOUT_INTENT = "checkout_intent", "Intention d'achat (Stripe)"
    PRODUCT_LEAD = "product_lead", "Lead produit"

class LeadStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    VALID = "VALID", "Validé"
    REJECTED = "REJECTED", "Rejeté"
    FAILED_TEMP = "FAILED_TEMP", "Echec temporaire"

class RejectReason(models.TextChoices):
    HONEYPOT = "HONEYPOT", "Honeypot rempli"
    ANTIFORGERY = "ANTIFORGERY", "Token HMAC invalide/expiré"
    RATE_LIMIT = "RATE_LIMIT", "Trop de requêtes"
    INVALID = "INVALID", "Données invalides"
    DUPLICATE = "DUPLICATE", "Doublon"
    DISPOSABLE = "DISPOSABLE", "Email jetable"