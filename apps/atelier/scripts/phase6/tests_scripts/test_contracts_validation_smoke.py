# apps/atelier/scripts/phase6/contracts_validation_smoke.py
from django.test.client import RequestFactory
from django.contrib.auth.models import AnonymousUser
from apps.atelier.components.contracts import validate
from apps.atelier.compose.hydration import load as hydrate
from apps.common.runscript_harness import binary_harness

ALIASES = [
    "header/struct",
    "hero/cover",
    "content_training",
    "course_list",
    "video_presentation",
    "proofbar/videos",
    "cta/primary",
    "footer/main",
    "modals/subscribe",
]

@binary_harness
def run():
    print("=== phase6/contracts_validation_smoke ===")
    rf = RequestFactory()
    req = rf.get("/")
    req.user = AnonymousUser()

    for a in ALIASES:
        ctx = hydrate(a, req)
        # En DEBUG=True, une erreur lèverait ; en prod, warning seulement.
        # Ici, on s’attend à des contextes valides selon les contrats déclarés.
        validate(a, ctx)
        print(f"[OK] {a} contract validated")
    print("=> PASS ✅")
