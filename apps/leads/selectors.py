from .models import Lead

def last_similar_lead(kind: str, email: str):
    return Lead.objects.filter(form_kind=kind, email=email).order_by("-created_at").first()