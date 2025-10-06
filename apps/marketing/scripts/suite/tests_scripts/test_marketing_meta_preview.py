# apps/marketing/scripts/marketing_meta_preview.py
"""
runscript marketing_meta_preview
"""
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone
from apps.catalog.models.models import Course
import re
from apps.common.runscript_harness import binary_harness

User = get_user_model()

def ensure_staff():
    u, _ = User.objects.get_or_create(
        username="seo_staff",
        defaults=dict(is_staff=True, is_superuser=True, email="staff@example.com")
    )
    u.set_password("pass1234")
    u.save()
    return u

def ensure_unpublished_course():
    slug = "seo-preview-unpublished"
    obj, created = Course.objects.get_or_create(
        slug=slug,
        defaults=dict(
            title="SEO Preview Unpublished",
            description="Test preview noindex.",
            is_published=False,
            seo_title="Preview Unpublished Title",
            seo_description="Preview Unpublished Description",
        ),
    )
    return obj

@binary_harness
def run():
    c = Client()
    user = ensure_staff()
    logged = c.login(username=user.username, password="pass1234")
    print("login staff:", logged)

    course = ensure_unpublished_course()
    url = course.get_absolute_url() + "?preview=1"
    r = c.get(url)
    print(f"[GET] {url} =>", r.status_code)
    if r.status_code != 200:
        print("FAIL: statut != 200")
        return

    html = r.content.decode("utf-8", "ignore")
    robots_ok = bool(re.search(
        r'<meta[^>]+name=["\']robots["\'][^>]+content=["\']([^"\']*noindex[^"\']*)',
        html, flags=re.I
    ))
    print("robots noindex:", "OK" if robots_ok else "FAIL")
    if robots_ok:
        print("OK: preview => noindex bien présent.")
    else:
        print("FAIL: robots noindex absent en preview staff.")