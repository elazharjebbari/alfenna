# apps/atelier/scripts/phase3/composer_warmup.py
"""
WARMUP simple: rend la page online_home pour remplir le cache des slots.
Exécution:
  - python manage.py runscript phase3.composer_warmup
"""

from django.test import RequestFactory
from django.contrib.auth.models import AnonymousUser
from apps.atelier.compose.pipeline import render_page
from apps.common.runscript_harness import binary_harness

@binary_harness
def run():
    rf = RequestFactory()
    req = rf.get("/", HTTP_ACCEPT_LANGUAGE="fr")
    req.user = AnonymousUser()
    res = render_page(req, "online_home", content_rev="rev1")
    warmed = len(res.get("fragments", {}))
    print(f"WARMED fragments: {warmed}")