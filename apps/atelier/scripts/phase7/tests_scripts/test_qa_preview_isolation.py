"""
Vérifie que le cache est isolé en mode preview (clés distinctes).
Exécution: python manage.py runscript phase7.qa_preview_isolation
"""
from django.test.client import RequestFactory
from django.contrib.auth.models import AnonymousUser
from apps.atelier.compose import pipeline
from apps.common.runscript_harness import binary_harness

@binary_harness
def run():
    print("=== phase7/qa_preview_isolation ===")
    rf = RequestFactory()

    req_std = rf.get("/")
    req_std.user = AnonymousUser()
    ctx_std = pipeline.build_page_spec("online_home", req_std)
    key_std = ctx_std["slots"]["hero"].get("cache_key")

    req_prev = rf.get("/?dwft_hero_v2=1")
    req_prev.user = AnonymousUser()
    ctx_prev = pipeline.build_page_spec("online_home", req_prev)
    key_prev = ctx_prev["slots"]["hero"].get("cache_key")

    print("std =", key_std)
    print("prev=", key_prev)
    assert key_std != key_prev and key_prev.endswith("|qa")
    print("=> PASS ✅")