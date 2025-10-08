from django.test import Client


def run() -> dict[str, object]:
    client = Client()
    response = client.get("/fr/produits/pack-cosmetique-naturel/")
    html = response.content.decode("utf-8", "ignore") if response.status_code == 200 else ""
    ok = response.status_code == 200 and "gallery-main swiper" in html and "<picture" in html
    result = {"ok": ok, "status": response.status_code, "len": len(html)}
    print(result)
    return result


if __name__ == "__main__":
    run()
