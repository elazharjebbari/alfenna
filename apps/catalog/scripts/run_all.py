import json

from django.core.management import call_command
from django.test import Client


def run() -> dict[str, object]:
    logs: list[str] = []
    try:
        call_command("loaddata", "apps/catalog/fixtures/products_pack_cosmetique.json", verbosity=0)
        logs.append("fixtures loaded")

        from apps.catalog.models import Product

        product = Product.objects.filter(slug="pack-cosmetique-naturel", is_active=True).first()
        logs.append(f"db lookup => {'OK' if product else 'MISSING'}")

        client = Client()
        response = client.get("/fr/produits/pack-cosmetique-naturel/", follow=True)
        logs.append(f"GET produit => {response.status_code}")
        html = response.content.decode("utf-8", "ignore") if response.status_code == 200 else ""
        ok = response.status_code == 200 and product and product.name in html
        return {"ok": ok, "logs": logs}
    except Exception as exc:  # pragma: no cover - convenience script
        logs.append(f"error: {exc}")
        return {"ok": False, "logs": logs}


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
