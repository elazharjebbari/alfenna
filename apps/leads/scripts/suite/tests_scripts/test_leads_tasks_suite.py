"""
runscript leads_tasks_suite

Objectif :
- Rejouer les scénarios clés de test_tasks via l’appel direct de la tâche Celery.
- Variables codées en dur pour reproductibilité.

Lancer :
  python manage.py runscript leads_tasks_suite
"""

from django.utils import timezone
from apps.leads.models import Lead
from apps.leads.constants import LeadStatus
from apps.leads.tasks import process_lead
from apps.common.runscript_harness import binary_harness


# =========================
# Configuration "en dur"
# =========================
EMAIL_TASK = "task@example.com"
EMAIL_TASK_DUP = "task@example.com"  # même email pour tester la dédup
KIND = "email_ebook"                 # forme simple => score attendu >= 10


@binary_harness
def run():
    print("\n== Nettoyage minimal ==")
    Lead.objects.filter(email__in=[EMAIL_TASK, EMAIL_TASK_DUP], form_kind=KIND).delete()

    # --- Scénario 1 : Traitement d’un lead PENDING => VALID + score ---
    print("\n[1] Traitement simple => VALID + score")
    lead = Lead.objects.create(
        form_kind=KIND,
        email=EMAIL_TASK,
        idempotency_key="task-k1",
        status=LeadStatus.PENDING,
        consent=True,
        consent_ip="127.0.0.1",
        consent_user_agent="runscript-tests/1.0",
        client_ts=timezone.now(),
    )
    print("Lead créé id=", lead.id, "status=", lead.status)

    process_lead(lead.id)
    lead.refresh_from_db()
    print("Après task: status=", lead.status, "score=", lead.score, "enriched_at=", lead.enriched_at)

    if lead.status == LeadStatus.VALID and lead.score >= 10.0:
        print("OK: lead validé et scoré")
    else:
        print("ATTENTION: le lead aurait dû être VALID avec score >= 10")

    # --- Scénario 2 : Doublon récent => REJECTED (DUPLICATE) ---
    print("\n[2] Déduplication récente => REJECTED/DUPLICATE")
    dup = Lead.objects.create(
        form_kind=KIND,
        email=EMAIL_TASK_DUP,  # même email + même kind → fingerprint identique
        idempotency_key="task-k2",
        status=LeadStatus.PENDING,
        consent=True,
        consent_ip="127.0.0.1",
        consent_user_agent="runscript-tests/1.0",
        client_ts=timezone.now(),
    )
    print("Lead dup id=", dup.id, "status=", dup.status)

    process_lead(dup.id)
    dup.refresh_from_db()
    print("Après task: status=", dup.status, "reject_reason=", dup.reject_reason)

    if dup.status == LeadStatus.REJECTED and dup.reject_reason == "DUPLICATE":
        print("OK: déduplication confirmée")
    else:
        print("ATTENTION: ce lead devait être REJETÉ pour DUPLICATE")

    print("\n== FIN SUITE TASKS ==")
