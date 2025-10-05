from django.dispatch import Signal

lead_validated = Signal()  # payload: lead
lead_rejected = Signal()   # payload: lead, reason
lead_enriched = Signal()   # payload: lead
# (brancher si besoin dans tasks/services)