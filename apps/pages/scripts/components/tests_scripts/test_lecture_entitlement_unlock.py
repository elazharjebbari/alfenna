import re
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from apps.atelier.config.loader import clear_config_cache
from apps.billing.services import PaymentService
from apps.billing.webhooks import _process_event
from apps.catalog.models.models import Course
from apps.common.runscript_harness import binary_harness
from apps.content.scripts import seed_stream_demo


@binary_harness
def run(*args, **kwargs):
    clear_config_cache()
    seed_stream_demo.run()

    course = Course.objects.get(slug="stream-demo")

    user, _ = User.objects.get_or_create(username="buyer_ok", defaults={"email": "buyer@example.com"})
    user.set_password("unlock")
    user.save()

    client = Client()
    assert client.login(username="buyer_ok", password="unlock"), "Login should succeed"

    mock_pi = {"id": "pi_test_unlock", "client_secret": "secret_test"}
    with patch("apps.billing.services.stripe.PaymentIntent.create", return_value=mock_pi), \
         patch("apps.billing.services.stripe.PaymentIntent.modify", return_value=mock_pi):
        order, _ = PaymentService.create_or_update_order_and_intent(
            user=user,
            email=user.email,
            course=course,
            currency="EUR",
        )

    event = {
        "type": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": order.stripe_payment_intent_id,
                "metadata": {"order_id": str(order.id)},
                "payment_method": "pm_test",
                "latest_charge": "ch_test",
                "status": "succeeded",
                "amount_received": order.amount_total,
                "currency": order.currency.lower(),
            }
        },
    }
    _process_event(event)

    url = reverse("pages:lecture", kwargs={"course_slug": course.slug})
    response = client.get(url)

    assert response.status_code == 200, f"Entitled user should access page, got {response.status_code}"
    html = response.content.decode("utf-8")

    assert 'data-locked="0"' in html, "Locked flag should be disabled for entitled user"

    match = re.search(r'<source[^>]*data-src="([^"]+)"', html)
    assert match and match.group(1), "Video source should be populated"

    return {"ok": True, "name": "lecture_entitlement_unlock", "duration": 0.0, "logs": []}
