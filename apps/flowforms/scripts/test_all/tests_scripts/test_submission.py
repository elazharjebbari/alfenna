import time
from django.conf import settings
from django.test.utils import get_runner
from apps.common.runscript_harness import binary_harness

@binary_harness
def run():
    """
    Valide la phase 7 (soumission vers leads) en lançant :
      - tests unitaires du service de soumission (apps.leads.tests.test_submission_service)
      - tests d’intégration wizard→soumission (apps.flowforms.tests.test_finalization)
    """
    start = time.time()
    result = {"name": "Phase 7 — Submission to Leads", "ok": True, "logs": []}

    TestRunner = get_runner(settings)
    runner = TestRunner(verbosity=2, failfast=False)
    try:
        failures = runner.run_tests([
            "apps.leads.tests.test_submission_service",
            "apps.flowforms.tests.test_finalization",
        ])
        result["ok"] = failures == 0
        result["logs"].append(f"Failures: {failures}")
    except Exception as e:
        result["ok"] = False
        result["logs"].append(f"Exception: {e}")

    result["duration"] = round(time.time() - start, 2)
    return result
