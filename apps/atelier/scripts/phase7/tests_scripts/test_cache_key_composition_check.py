"""
Vérifie la composition complète de la clé (ordre & champs) + suffixe |qa en preview.
Exécution: python manage.py runscript phase7.cache_key_composition_check
"""
from django.test.client import RequestFactory
from django.contrib.auth.models import AnonymousUser

from apps.atelier import services
from apps.atelier.compose import pipeline
from apps.common.runscript_harness import binary_harness

@binary_harness
def run():
    print("=== phase7/cache_key_composition_check ===")
    rf = RequestFactory()

    # Standard
    req = rf.get("/", HTTP_ACCEPT_LANGUAGE="fr-FR,fr;q=0.9", HTTP_USER_AGENT="Mozilla/5.0")
    req.user = AnonymousUser()
    req.COOKIES = {"consent": "Y"}

    page_ctx = pipeline.build_page_spec("online_home", req)
    hero = page_ctx["slots"]["hero"]
    key = hero.get("cache_key") or ""
    print("key std =", key)
    # 9 parties (sans |qa)
    parts = key.split("|")
    assert len(parts) in (9, 10), f"Nombre de parties inattendu: {len(parts)}"
    # route,slot,variant,lang,device,consent,source,campaign,content_rev[,qa]
    assert parts[0] == "online_home" and parts[1] == "hero" and parts[2] in ("A", "B")
    assert parts[3] in ("fr", "en")
    assert parts[4] in ("d", "m")
    assert parts[5] in ("Y", "N")

    # Preview QA
    req2 = rf.get("/?dwft_hero_v2=1", HTTP_ACCEPT_LANGUAGE="fr", HTTP_USER_AGENT="Mobile")
    req2.user = AnonymousUser()
    req2.COOKIES = {"consent": "N"}
    page_ctx2 = pipeline.build_page_spec("online_home", req2)
    hero2 = page_ctx2["slots"]["hero"]
    key2 = hero2.get("cache_key") or ""
    print("key qa =", key2)
    assert key != key2, "La preview doit produire une clé distincte"
    assert key2.endswith("|qa"), "La clé preview doit se terminer par |qa"

    print("=> PASS ✅")