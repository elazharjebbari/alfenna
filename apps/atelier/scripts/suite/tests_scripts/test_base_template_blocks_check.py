# apps/atelier/scripts/base_template_blocks_check.py
from django.template import loader
from django.utils.safestring import mark_safe
from apps.common.runscript_harness import binary_harness

BLOCKS = [
    "tags_header",
    "meta_header",
    "styles",
    "extra_css",
    "extra_head",
    "tags_body",
    "header",
    "messages",
    "content",
    "sidebar",
    "footer",
    "scripts",
    "js",
    "before_end_body",
]

PATTERNS = [
    # on tolère {% block name %} et {% block name  %}
    # et éventuellement {% endblock name %}
    lambda name: "{% block " + name,
]

@binary_harness
def run():
    print("=== base_template_blocks_check: START ===")
    t = loader.get_template("base.html")
    # on récupère la source via origin quand possible
    src = ""
    try:
        with open(t.origin.name, "r", encoding="utf-8") as f:
            src = f.read()
    except Exception:
        # fallback : str(template) ne donne pas la source ; on fail soft
        print("[WARN] Impossible de lire la source via origin; vérification best-effort.")
        src = str(t)

    ok = True
    for name in BLOCKS:
        found = any(p(name) in src for p in PATTERNS)
        if found:
            print(f"[FOUND] block `{name}`")
        else:
            ok = False
            print(f"[MISS]  block `{name}` non trouvé")

    print(f"=== base_template_blocks_check: {'PASS' if ok else 'FAIL'} ===")