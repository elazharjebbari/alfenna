"""
Orchestrateur global FlowForms
Exécution:
  python manage.py runscript apps.flowforms.scripts.run_flowforms_all
"""
from apps.flowforms.scripts.test_all import run_all as test_all_run_all

def run():
    test_all_run_all.run()
