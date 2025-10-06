import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "alfenna.settings.prod")  # ou base/dev selon l'env

app = Celery("alfenna")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

existing_imports = tuple(getattr(app.conf, "imports", ()) or ())
app.conf.imports = existing_imports + ("apps.messaging.tasks_debug",)

# Optionnel : health/maintenance tasks (ex : purges, métriques)
app.conf.beat_schedule = getattr(app.conf, "beat_schedule", {})
app.conf.beat_schedule.update({
    # Exemple: purge des leads rejetés âgés > 90 jours (si tu ajoutes la task)
    # "leads-purge-rejected": {
    #     "task": "apps.leads.tasks.purge_rejected_old",
    #     "schedule": crontab(hour=4, minute=0),
    # },
})
