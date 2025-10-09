import time
from typing import Dict

from django.test import Client
from django.urls import reverse

from apps.catalog.models import Product


NAME = "fab_whatsapp_smoke"


def _ensure_product() -> Product:
    product, _ = Product.objects.get_or_create(
        slug="pack-cosmetique-naturel",
        defaults={
            "name": "Pack Cosmétiques",
            "price": 349,
            "promo_price": 329,
            "currency": "MAD",
        },
    )
    return product


def run() -> Dict[str, object]:
    started = time.time()
    client = Client()
    product = _ensure_product()
    url = reverse("pages:product-detail-slug", kwargs={"product_slug": product.slug})
    response = client.get(url)
    html = response.content.decode()
    ok = response.status_code == 200 and 'data-cmp="fab-whatsapp"' in html
    logs = f"status={response.status_code}"
    if ok:
        logs += ", fab_whatsapp detected"
    else:
        logs += ", fab_whatsapp missing"
    return {
        "ok": ok,
        "name": NAME,
        "duration": round(time.time() - started, 3),
        "logs": logs,
    }
