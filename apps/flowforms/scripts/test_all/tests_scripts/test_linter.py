import time
from django.core.management import call_command
from apps.common.runscript_harness import binary_harness

@binary_harness
def run():
    start = time.time()
    result = {"name": "FlowForms Linter", "ok": True, "logs": []}
    try:
        call_command("flowforms_lint")
        result["logs"].append("flowforms_lint OK")
    except SystemExit as e:
        result["ok"] = False
        result["logs"].append(f"Linter exited with {e.code}")
    except Exception as e:
        result["ok"] = False
        result["logs"].append(f"Exception: {e}")

    result["duration"] = round(time.time() - start, 2)
    return result