import time
from django.utils.module_loading import import_string
from apps.common.runscript_harness import binary_harness

@binary_harness
def run():
    start = time.time()
    result = {"name": "Pre-flight", "ok": True, "logs": []}

    try:
        task = import_string("apps.flowforms.tasks.debug_ping")
        res = task.apply(kwargs={"echo": "preflight"})
        result["logs"].append(f"Celery ping result: {res.get()}")
        if res.failed():
            result["ok"] = False
            result["logs"].append("Ping FAILED")
    except Exception as e:
        result["ok"] = False
        result["logs"].append(f"Exception: {e}")

    result["duration"] = round(time.time() - start, 2)
    return result