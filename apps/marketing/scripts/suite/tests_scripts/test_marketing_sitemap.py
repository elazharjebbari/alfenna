# apps/marketing/scripts/marketing_sitemap.py
"""
runscript marketing_sitemap
"""
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from apps.catalog.models.models import Course
import re
from apps.common.runscript_harness import binary_harness

def ensure_course():
    slug = "seo-sitemap-demo"
    obj, created = Course.objects.get_or_create(
        slug=slug,
        defaults=dict(
            title="SEO Sitemap Demo",
            description="Cours de démonstration pour sitemap.",
            is_published=True,
            published_at=timezone.now(),
            seo_title="SEO Sitemap Demo",
            seo_description="Meta description sitemap demo.",
        ),
    )
    return obj

def fetch_sitemap_urls(html: bytes):
    text = html.decode("utf-8", "ignore")
    # Récupère <loc>…</loc>
    return re.findall(r"<loc>(.*?)</loc>", text, flags=re.I)

@binary_harness
def run():
    c = Client()
    course = ensure_course()
    expected_path = course.get_absolute_url()  # ex: /cours/<slug>/

    # 1) sitemap index ou direct
    r = c.get("/sitemap.xml")
    print("[GET] /sitemap.xml =>", r.status_code)
    if r.status_code != 200:
        print("FAIL: statut != 200")
        return

    locs = fetch_sitemap_urls(r.content)
    if any(expected_path in loc for loc in locs):
        print("OK: URL cours présente directement dans l’index.")
        return

    # 2) si index: suivre les sous-sitemaps
    matched = False
    for loc in locs:
        if not loc:
            continue
        # Simple heuristique : extraire le chemin relatif si loc est absolu
        path = loc
        if loc.startswith("http"):
            from urllib.parse import urlparse
            u = urlparse(loc)
            path = u.path
        rr = c.get(path)
        print(f"[GET] {path} =>", rr.status_code)
        if rr.status_code != 200:
            continue
        sublocs = fetch_sitemap_urls(rr.content)
        if any(expected_path in s for s in sublocs):
            matched = True
            print("OK: URL cours trouvée dans un sous-sitemap.")
            break

    if not matched:
        print("FAIL: URL cours non trouvée dans les sitemaps.")