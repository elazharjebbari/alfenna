from __future__ import annotations

from django.template.loader import get_template

from apps.common.runscript_harness import binary_harness


@binary_harness
def run():
    template = get_template("screens/product_detail.html")
    source = open(template.origin.name, "r", encoding="utf-8").read()
    required_tokens = [
        'data-ll-slot-id="vendors"',
        'data-ll-slot-id="header"',
        'data-ll-slot-id="product_hero"',
        'data-ll-slot-id="sticky_buybar_v2"',
        'data-ll-slot-id="before_after_wipe"',
        'data-ll-slot-id="gallery"',
        'data-ll-slot-id="faq"',
    ]
    missing = [token for token in required_tokens if token not in source]
    ok = not missing
    logs = [] if ok else ["Missing: " + ", ".join(missing)]
    return {"ok": ok, "name": "pd_wrappers_present", "duration": 0.0, "logs": logs}
