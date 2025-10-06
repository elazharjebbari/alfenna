from django.contrib.auth.models import User
from apps.catalog.models.models import Course
from apps.billing.services import PaymentService
from apps.common.runscript_harness import binary_harness

@binary_harness
def run(*args):
    print('== billing_currency: start ==')
    u, _ = User.objects.get_or_create(username='buyer_currency', defaults={'email':'c@example.com'})
    c = Course.objects.filter(is_published=True).first()
    assert c, 'Seed un course publié'

    for cur in ('EUR','USD'):
        order, payload = PaymentService.create_or_update_order_and_intent(user=u, email=u.email, course=c, currency=cur)
        assert order.currency == cur, f"currency mismatch {order.currency}"
        assert order.amount_total > 0, 'amount_total should be > 0'
    print('== billing_currency: OK ✅ ==')