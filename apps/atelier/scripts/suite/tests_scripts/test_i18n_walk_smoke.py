from __future__ import annotations

from apps.atelier.i18n.service import i18n_walk
from apps.common.runscript_harness import binary_harness


@binary_harness
def run():
    payload = {"label": "t:footer.shop"}
    translated = i18n_walk(payload, locale="ar", site_version="ma")
    ok = translated["label"] not in {payload["label"], "t:footer.shop"}

    logs = {
        "payload": payload,
        "translated": translated,
    }

    return {"ok": ok, "name": "i18n_walk_smoke", "logs": [logs]}
