from django.utils import timezone
from apps.catalog.models.models import Course, CoursePrice

def run(*args):
    print("== catalog_prices_seed: start ==")
    c = Course.objects.filter(is_published=True).first()
    assert c, "Crée un cours publié d'abord (catalog_seed)."
    created = 0
    for cur, cents in [("EUR", 9900), ("USD", 10900)]:
        obj, was = CoursePrice.objects.get_or_create(
            course=c, currency=cur, country=None, active=True,
            defaults={"amount_cents": cents, "effective_at": timezone.now()}
        )
        created += 1 if was else 0
    print(f"seeded={created}")
    print("== catalog_prices_seed: OK ✅ ==")
