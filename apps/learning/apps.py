import logging
import os
import sys

from django.apps import AppConfig
from django.core.management import call_command
from django.db.utils import OperationalError, ProgrammingError


log = logging.getLogger(__name__)


class LearningConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.learning'

    def ready(self):
        disabled = os.environ.get("DISABLE_BOUGIES_AUTOLOAD", "").lower() in {"1", "true", "yes"}
        if disabled:
            return
        skip_commands = {"makemigrations", "migrate", "collectstatic", "shell", "loaddata", "dumpdata", "test", "runscript"}
        if any(cmd in sys.argv for cmd in skip_commands):
            return
        try:
            from apps.catalog.models.models import Course

            if Course.objects.filter(slug="bougies-naturelles").exists():
                return

            call_command("loaddata", "alfenna/fixtures/course_bougies.json", verbosity=0)
        except (OperationalError, ProgrammingError):
            # Database not ready yet
            pass
        except Exception:  # pragma: no cover
            log.exception("Unable to preload bougies course fixture")
