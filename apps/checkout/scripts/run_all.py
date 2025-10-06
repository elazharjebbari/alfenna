from __future__ import annotations

import json
from typing import Any, Dict

from django.test import Client


def _post_json(client: Client, url: str, data: Dict[str, Any], **extra) -> Any:
    return client.post(url, data=json.dumps(data), content_type="application/json", **extra)


def run() -> None:
    client = Client()

    payload = {
        "payment_method": "online",
        "form_kind": "product_lead",
        "full_name": "Test User",
        "phone": "+212600000000",
        "context": {"utm_source": "script"},
    }

    response = _post_json(client, "/api/checkout/sessions/", payload)
    print("[checkout] status=", response.status_code, "body=", response.content.decode())


if __name__ == "__main__":
    run()
