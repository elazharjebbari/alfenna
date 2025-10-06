from __future__ import annotations

from apps.messaging.models import EmailTemplate
from apps.messaging.template_loader import FileSystemTemplateLoader


def run():
    loader = FileSystemTemplateLoader()
    templates = loader.sync()
    slugs = sorted({tpl.slug for tpl in templates})
    return {
        "ok": bool(templates),
        "name": "test_template_catalog",
        "duration": 0.0,
        "logs": [f"loaded={len(templates)}", "slugs=" + ",".join(slugs[:5])],
    }
