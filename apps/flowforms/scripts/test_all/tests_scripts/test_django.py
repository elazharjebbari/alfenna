import time
from django.conf import settings
from django.test.utils import get_runner
from apps.common.runscript_harness import binary_harness

@binary_harness
def run():
    start = time.time()
    result = {"name": "Django tests", "ok": True, "logs": []}

    TestRunner = get_runner(settings)
    runner = TestRunner(verbosity=2, failfast=False)
    try:
        failures = runner.run_tests(["apps.flowforms", "apps.leads"])
        result["ok"] = failures == 0
        result["logs"].append(f"Failures: {failures}")
    except Exception as e:
        result["ok"] = False
        result["logs"].append(f"Exception: {e}")

    result["duration"] = round(time.time() - start, 2)
    return result