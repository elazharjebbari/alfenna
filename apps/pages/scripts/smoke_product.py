"""Smoke tests for the product detail experience."""

from __future__ import annotations

from django.test import Client, RequestFactory

from apps.atelier.compose.hydrators.product.product import hydrate_product

PRODUCT_URLS = (
    "/produits/",
    "/produits/sajadat-al-raha",
)


def run(*args) -> None:  # pragma: no cover - manual smoke helper
    client = Client()
    for url in PRODUCT_URLS:
        response = client.get(url, follow=True)
        html = response.content.decode()
        status = response.status_code
        has_component = "data-cmp=\"product\"" in html
        has_stepper = "data-form-stepper" in html and 'data-steps="3"' in html
        has_signed = 'data-sign-url="/api/leads/sign/"' in html and 'data-require-signed="true"' in html
        slides = html.count("swiper-slide")
        slides_ok = slides >= 1
        print(
            f"{url} status={status} slides={slides}"
            f" component={'OK' if has_component else 'KO'}"
            f" stepper={'OK' if has_stepper else 'KO'}"
            f" signed={'OK' if has_signed else 'KO'}"
            f" media={'OK' if slides_ok else 'KO'}"
        )

    factory = RequestFactory()
    request = factory.get("/produits/")
    request.site_version = "core"
    ctx = hydrate_product(request, {"product": {"id": "sku", "name": "Produit"}, "media": {"images": []}})
    images = ctx["media"].get("images") or []
    if len(images) != 3:
        print("fallback media check: KO (expected 3 placeholders)")
    else:
        thumbs_ok = all(item.get("thumb") for item in images)
        slides_ok = all(item.get("src") for item in images)
        status = "OK" if thumbs_ok and slides_ok else "KO"
        print(f"fallback media check: {status}")
