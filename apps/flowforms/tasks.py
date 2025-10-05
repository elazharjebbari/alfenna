from celery import shared_task
from django.utils import timezone

@shared_task(bind=True, autoretry_for=(), retry_backoff=False)
def debug_ping(self, echo: str = "pong") -> dict:
    """
    Tâche Celery no-op pour vérifier l’intégration côté tests.
    S’exécute en local via .apply() (synchrone) sans worker.
    """
    return {"echo": echo, "now": timezone.now().isoformat()}