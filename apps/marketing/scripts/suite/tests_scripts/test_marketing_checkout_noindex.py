# apps/marketing/scripts/marketing_checkout_noindex.py
"""
runscript marketing_checkout_noindex
"""
from types import SimpleNamespace
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone
from apps.catalog.models.models import Course
from apps.common.runscript_harness import binary_harness

User = get_user_model()

def ensure_user():
    u, _ = User.objects.get_or_create(
        username="seo_buyer",
        defaults=dict(email="buyer@example.com")
    )
    u.set_password("pass1234")
    u.save()
    return u

def ensure_course():
    slug = "seo-checkout-demo"
    obj, _ = Course.objects.get_or_create(
        slug=slug,
        defaults=dict(
            title="SEO Checkout Demo",
            description="Page de paiement — doit être noindex.",
            is_published=True,
            published_at=timezone.now(),
            seo_title="Checkout Meta Title",
            seo_description="Checkout meta description.",
        ),
    )
    return obj

@binary_harness
def run():
    c = Client()
    user = ensure_user()
    c.login(username=user.username, password="pass1234")
    course = ensure_course()

    # Monkeypatch PaymentService dans la vue (évite Stripe)
    import apps.billing.views.views as billing_views

    def stub_create_or_update_order_and_intent(*, user=None, email="", course=None, price_plan=None, currency="EUR", existing_order=None, **kwargs):
        fake_order = SimpleNamespace(amount_total=12345, currency=currency)
        payload = {"client_secret": "cs_test_123", "publishable_key": "pk_test_123"}
        return fake_order, payload

    original = billing_views.PaymentService.create_or_update_order_and_intent
    billing_views.PaymentService.create_or_update_order_and_intent = stub_create_or_update_order_and_intent

    try:
        url = f"/billing/checkout/{course.slug}/"
        r = c.get(url)
        print(f"[GET] {url} =>", r.status_code)
        if r.status_code != 200:
            print("FAIL: statut != 200")
            return
        html = r.content.decode("utf-8", "ignore")
        import re
        robots_ok = bool(re.search(
            r'<meta[^>]+name=["\']robots["\'][^>]+content=["\']([^"\']*noindex[^"\']*)',
            html, flags=re.I
        ))
        print("robots noindex:", "OK" if robots_ok else "FAIL")
        if robots_ok:
            print("OK: checkout => noindex bien présent.")
        else:
            print("FAIL: robots noindex absent sur checkout.")
    finally:
        # Restore
        billing_views.PaymentService.create_or_update_order_and_intent = original
