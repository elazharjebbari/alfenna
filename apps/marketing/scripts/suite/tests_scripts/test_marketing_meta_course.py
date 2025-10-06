# apps/marketing/scripts/marketing_meta_course.py
"""
runscript marketing_meta_course
"""
from django.test import Client
from django.utils import timezone
from apps.catalog.models.models import Course
import re
from apps.common.runscript_harness import binary_harness

def ensure_course():
    slug = "seo-course-meta"
    obj, created = Course.objects.get_or_create(
        slug=slug,
        defaults=dict(
            title="SEO Course Meta",
            description="Une page cours pour tester les balises meta.",
            is_published=True,
            published_at=timezone.now(),
            seo_title="SEO Course Meta Title",
            seo_description="SEO Course Meta Description.",
        ),
    )
    return obj

def find_one(pattern, html):
    m = re.search(pattern, html, flags=re.I|re.S)
    return bool(m)

@binary_harness
def run():
    c = Client()
    course = ensure_course()
    url = course.get_absolute_url()
    r = c.get(url)
    html = r.content.decode("utf-8", "ignore")
    print(f"[GET] {url} =>", r.status_code)
    if r.status_code != 200:
        print("FAIL: statut != 200")
        return

    checks = {
        "title": r"<title>.*SEO Course Meta Title.*</title>",
        "meta_description": r'<meta[^>]+name=["\']description["\'][^>]+content=["\'].*SEO Course Meta Description',
        "og_title": r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\'].*SEO Course Meta Title',
        "canonical": r'<link[^>]+rel=["\']canonical["\'][^>]+href=',
        "jsonld": r'<script[^>]+type=["\']application/ld\+json["\']',
    }

    all_ok = True
    for name, pat in checks.items():
        ok = find_one(pat, html)
        print(f"{name}: {'OK' if ok else 'FAIL'}")
        all_ok &= ok

    if all_ok:
        print("OK: meta de la page cours correctes.")
    else:
        print("WARN: certaines balises meta manquent (vérifie l’intégration base.html/_seo_head.html).")