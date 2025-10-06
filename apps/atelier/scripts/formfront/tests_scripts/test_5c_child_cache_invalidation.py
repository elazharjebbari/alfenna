# apps/atelier/scripts/formfront/tests_scripts/test_5c_child_cache_invalidation.py
from __future__ import annotations
import time
from django.test.client import RequestFactory
from apps.atelier.components.forms.wizard.hydrators import hydrate
from apps.common.runscript_harness import binary_harness

NAME = "Étape 5.C — Invalidation (variation sémantique → SHA1 change)"

@binary_harness
def run():
    t0 = time.time(); logs = []; ok = True
    rf = RequestFactory()

    # Base
    cfg_a = '{"flow_key":"A","endpoint_url":"/api","form_kind":"alpha","context":{}}'
    cfg_b = '{"flow_key":"A","endpoint_url":"/api","form_kind":"beta","context":{}}'  # diffère sémantiquement (form_kind)

    c_a1 = hydrate(rf.get("/"), params={"flow_key":"A", "config_json": cfg_a})
    c_a2 = hydrate(rf.get("/"), params={"flow_key":"B", "config_json": cfg_a})  # flow_key diffère, config identique
    c_b  = hydrate(rf.get("/"), params={"flow_key":"A", "config_json": cfg_b})

    # 1) Changer **uniquement** flow_key → SHA1 doit rester identique (flow_key n'entre pas dans le hash)
    if c_a1["config_sha1"] != c_a2["config_sha1"]:
        ok = False; logs.append("❌ Changement de flow_key a changé le SHA1 (attendu identique)")

    # 2) Changement **sémantique** de config → SHA1 doit changer
    if c_a1["config_sha1"] == c_b["config_sha1"]:
        ok = False; logs.append("❌ Changement de config (form_kind) n'a pas modifié le SHA1")

    logs.append(f"sha1 A(flow=A)={c_a1['config_sha1']}  /  A(flow=B)={c_a2['config_sha1']}  /  B={c_b['config_sha1']}")
    return {"name": NAME, "ok": ok, "duration": round(time.time()-t0,2), "logs": logs}