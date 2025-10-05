from django.http import HttpResponse

from .helpers import build_base_url


def robots_txt(request):
    base = build_base_url(request)
    if not base:
        base = "https://example.com"
    lines = [
        "User-agent: *",
        "Disallow: /admin/",
        "Disallow: /accounts/",
        f"Sitemap: {base}/sitemap.xml",
        "",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")
