from django.test import Client
from django.urls import reverse

from apps.catalog.models import Product


def run():
    product, _ = Product.objects.get_or_create(
        slug="pack-cosmetique-naturel",
        defaults={
            "name": "Pack",
            "price": 349,
            "promo_price": 347,
            "currency": "MAD",
        },
    )

    url = reverse("pages:product-detail-slug", kwargs={"product_slug": product.slug})
    client = Client()
    response = client.get(url)

    ok = response.status_code == 200 and b"af-buybar-v2" in response.content
    status = "OK" if ok else "FAIL"
    print(f"[sticky_buybar_v2_smoke] {status} {url}")
