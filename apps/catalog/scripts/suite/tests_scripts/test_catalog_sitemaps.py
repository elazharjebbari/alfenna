from django.test import Client
from django.urls import reverse
from apps.catalog.models.models import Course
from apps.common.runscript_harness import binary_harness

@binary_harness
def run(*args):
    print("== catalog_sitemaps: start ==")
    c = Client()
    resp = c.get(reverse('sitemap'))
    assert resp.status_code == 200, f"Sitemap status {resp.status_code}"
    # Au moins un cours publié présent
    if Course.objects.filter(is_published=True).exists():
        any_slug = Course.objects.filter(is_published=True).values_list('slug', flat=True).first()
        assert any_slug.encode() in resp.content, "Slug de cours publié absent du sitemap"
    print("== catalog_sitemaps: OK ✅ ==")