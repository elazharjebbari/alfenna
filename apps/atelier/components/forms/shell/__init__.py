# apps/atelier/components/forms/shell/__init__.py
from __future__ import annotations

COMPONENT = {
    "alias": "forms/shell",
    "template": "components/forms/shell.html",
    "contracts": ["forms/shell"],
    "compose": {
        "children": {
            "wizard": "forms/wizard_generic",
        }
    },
    "render": {"cacheable": True},
}
