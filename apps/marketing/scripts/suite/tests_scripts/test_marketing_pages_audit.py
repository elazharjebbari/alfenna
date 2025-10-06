# apps/marketing/scripts/marketing_pages_audit.py
"""
runscript marketing_pages_audit
Audit multi-pages robuste : liste, détail cours, détail leçon (gating-aware), sitemap.
- Suit les redirections
- Retente la leçon en preview staff si gated
- Vérifie balises clés (title, meta description, OG, canonical, JSON-LD)
"""
from django.test import Client
from django.utils import timezone
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.catalog.models.models import Course
from apps.content.models import Section, Lecture
import re
from apps.common.runscript_harness import binary_harness

# ---------- helpers de fabrication de contenu ----------
def ensure_course_plan():
    slug = "seo-audit-course"
    course, _ = Course.objects.get_or_create(
        slug=slug,
        defaults=dict(
            title="SEO Audit Course",
            description="Cours de démo pour audit SEO.",
            is_published=True,
            published_at=timezone.now(),
            seo_title="SEO Audit Course Title",
            seo_description="SEO Audit Course Description.",
        ),
    )
    section, _ = Section.objects.get_or_create(
        course=course, order=1,
        defaults=dict(title="Introduction", is_published=True)
    )
    # On force une leçon marquée gratuite (si la politique le permet)
    lecture, _ = Lecture.objects.get_or_create(
        course=course, section=section, order=1,
        defaults=dict(title="Bienvenue", is_published=True, is_free=True, type="article")
    )
    return course, section, lecture

def ensure_staff():
    User = get_user_model()
    u, created = User.objects.get_or_create(
        username="seo_tester",
        defaults={"email": "seo_tester@example.com", "is_staff": True, "is_active": True}
    )
    # mot de passe fixe pour la session de test (non critique)
    if created or not u.has_usable_password():
        u.set_password("seo_tester")
        u.save(update_fields=["password"])
    return u

# ---------- parsing balises ----------
CHECKS = {
    "title": r"<title>.*?</title>",
    "meta_description": r'<meta[^>]+name=["\']description["\'][^>]*>',
    "og_title": r'<meta[^>]+property=["\']og:title["\'][^>]*>',
    "canonical": r'<link[^>]+rel=["\']canonical["\'][^>]*>',
    "jsonld": r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>',
}

def check_tags(html: str):
    results = {}
    for name, pat in CHECKS.items():
        results[name] = bool(re.search(pat, html, flags=re.I | re.S))
    return results

def summarize(results: dict) -> str:
    return ", ".join(f"{k}={'OK' if v else 'NO'}" for k, v in results.items())

# ---------- requêtage ----------
def get_follow(client: Client, url: str):
    """GET avec follow=True, pour récupérer la page finale + chaîne de redirects."""
    r = client.get(url, follow=True)
    final = r
    chain = getattr(r, "redirect_chain", [])
    # r.request peut être absent si rien n'a été rendu (rare), on protège.
    try:
        req = final.request
        final_url = req.get("PATH_INFO", "") + ("?" + req.get("QUERY_STRING", "") if req.get("QUERY_STRING") else "")
    except Exception:
        final_url = url
    return final, final_url, chain

def print_redirect_chain(chain):
    if not chain:
        return
    for (loc, code) in chain:
        print(f"      ↪ redirect {code} -> {loc}")

# ---------- RUN ----------
@binary_harness
def run():
    c = Client()
    course, section, lecture = ensure_course_plan()

    urls = [
        (reverse("catalog:list"), "catalogue (liste)", False),
        (course.get_absolute_url(), "cours (détail)", False),
        (reverse("content:lecture-detail", kwargs={
            "course_slug": course.slug, "section_order": section.order, "lecture_order": lecture.order
        }), "leçon (détail)", True),  # potentiellement gated
        ("/sitemap.xml", "sitemap", False),
    ]

    print("== Audit SEO multi-pages ==")

    # 1) pages simples (liste, cours, sitemap) + 2) leçon en anonyme
    for url, label, maybe_gated in urls:
        r, final_url, chain = get_follow(c, url)
        status = r.status_code
        print(f"[{status}] {label}: {url}")
        print_redirect_chain(chain)

        if url == "/sitemap.xml":
            # Pour le sitemap, on ne parse pas des balises HTML
            continue

        if status == 200:
            html = r.content.decode("utf-8", "ignore")
            results = check_tags(html)
            print("     ", summarize(results))
            # Si c'était la leçon et qu'on a 200 en anonyme, parfait.
            continue

        # Si la page peut être gated (leçon) et qu'on n'a pas 200, on tente le preview staff
        if maybe_gated:
            print("     Page potentiellement protégée. Tentative en mode preview staff…")
            staff = ensure_staff()
            c_staff = Client()
            c_staff.login(username=staff.username, password="seo_tester")
            sep = "&" if "?" in url else "?"
            url_preview = f"{url}{sep}preview=1"
            r2, final_url2, chain2 = get_follow(c_staff, url_preview)
            status2 = r2.status_code
            print(f"    [preview:{status2}] {final_url2}")
            print_redirect_chain(chain2)
            if status2 == 200:
                html2 = r2.content.decode("utf-8", "ignore")
                results2 = check_tags(html2)
                print("     ", summarize(results2))
            else:
                print("     WARN: même en preview staff, statut != 200 — vérifier la vue/middleware de gating.")
        else:
            print("     FAIL: statut != 200")

    print("== Fin audit ==")
