from __future__ import annotations

from apps.messaging.scripts import diagnostics


def run() -> dict:
    result = diagnostics.run()
    logs = result.get("logs", [])
    summary = logs[:3] if logs else ["diagnostics executed"]
    return {"ok": bool(result.get("ok")), "logs": summary}
