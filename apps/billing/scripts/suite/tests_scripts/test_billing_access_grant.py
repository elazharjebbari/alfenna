from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from apps.catalog.models.models import Course
from apps.billing.services import PaymentService
from apps.billing.webhooks import _process_event
from apps.common.runscript_harness import binary_harness

@binary_harness
def run(*args):
    print('== billing_access_grant: start ==')
    u, _ = User.objects.get_or_create(username='buyer_access', defaults={'email':'test@example.com'})
    u.set_password('Password-2025'); u.save()
    c = Client(); assert c.login(username='buyer_access', password='Password-2025')

    course = Course.objects.filter(is_published=True).first()
    assert course

    order, _ = PaymentService.create_or_update_order_and_intent(user=u, email=u.email, course=course, currency='EUR')

    # simuler webhook
    event = {"type": "payment_intent.succeeded", "data": {"object": {"id": order.stripe_payment_intent_id, "metadata": {"order_id": str(order.id)}}}}
    _process_event(event)

    # tenter l’accès premium (une leçon au-delà de free N)
    s = course.sections.order_by('order').last()
    lec = s.lectures.order_by('order').last()
    url = reverse('content:lecture', kwargs={'course_slug': course.slug, 'section_order': s.order, 'lecture_order': lec.order})
    r = c.get(url)
    assert r.status_code == 200, f"Premium should be unlocked, got {r.status_code}"
    print('== billing_access_grant: OK ✅ ==')