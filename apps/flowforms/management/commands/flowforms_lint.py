import sys
import inspect
from django.core.management.base import BaseCommand
from apps.flowforms.conf.loader import load_config
from apps.leads.models import Lead

class Command(BaseCommand):
    help = "Valide la config FlowForms (schéma + cross-checks avec Lead)."

    def handle(self, *args, **options):
        self.stdout.write("=== FlowForms Linter ===")

        try:
            cfg = load_config()
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Erreur parsing YAML: {e}"))
            sys.exit(1)

        # Liste des champs valides du modèle Lead
        lead_fields = {f.name for f in Lead._meta.get_fields() if hasattr(f, "name")}
        self.stdout.write(f"- Champs Lead détectés: {len(lead_fields)}")

        errors = []
        for flow in cfg.flows:
            self.stdout.write(self.style.NOTICE(f"Flow {flow.key} (kind={flow.kind})"))
            for step in flow.steps:
                for field in step.fields:
                    if not (field.name in lead_fields or field.name.startswith("context.")):
                        errors.append(f"Flow {flow.key}, step {step.key}, field {field.name} invalide")

        if errors:
            self.stderr.write(self.style.ERROR("❌ Erreurs détectées:"))
            for e in errors:
                self.stderr.write(f"  - {e}")
            sys.exit(1)
        else:
            self.stdout.write(self.style.SUCCESS("✅ Config valide."))