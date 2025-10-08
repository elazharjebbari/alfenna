from __future__ import annotations

from django.template.loader import get_template

from apps.common.runscript_harness import binary_harness


@binary_harness
def run():
    template = get_template("screens/product_detail.html")
    source = open(template.origin.name, "r", encoding="utf-8").read()
    required_slots = (
        "vendors",
        "header",
        "product_hero",
        "sticky_buybar_v2",
        "before_after_wipe",
        "gallery",
        "faq",
    )
    missing = []
    for slot in required_slots:
        token = f'data-ll-page-id="product_detail" data-ll-slot-id="{slot}"'
        if token not in source:
            missing.append(token)
    ok = not missing
    logs = [] if ok else ["Missing: " + ", ".join(missing)]
    return {"ok": ok, "name": "pd_wrappers_present", "duration": 0.0, "logs": logs}
