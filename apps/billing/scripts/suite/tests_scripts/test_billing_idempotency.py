from django.contrib.auth.models import User
from apps.catalog.models.models import Course
from apps.billing.models import Order, OrderStatus
from apps.billing.services import PaymentService
from apps.billing.webhooks import _process_event
from apps.common.runscript_harness import binary_harness

@binary_harness
def run(*args):
    print('== billing_idempotency: start ==')
    u, _ = User.objects.get_or_create(username='buyer_idemp', defaults={'email':'i@example.com'})
    c = Course.objects.filter(is_published=True).first()
    assert c

    order, _ = PaymentService.create_or_update_order_and_intent(user=u, email=u.email, course=c, currency='EUR')

    event = {"type": "payment_intent.succeeded", "data": {"object": {"id": order.stripe_payment_intent_id, "metadata": {"order_id": str(order.id)}}}}
    _process_event(event)
    _process_event(event)
    _process_event(event)

    order.refresh_from_db()
    assert order.status == OrderStatus.PAID
    print('== billing_idempotency: OK ✅ ==')