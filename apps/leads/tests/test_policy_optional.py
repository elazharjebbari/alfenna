import hashlib
import hmac
import json
import time
from uuid import uuid4

from django.conf import settings
from django.test import TestCase
from django.urls import reverse


def make_signed_token(payload: dict, *, age: int = 0) -> str:
    timestamp = int(time.time() - age)
    filtered = {key: value for key, value in payload.items() if key != "signed_token"}
    digest = hashlib.md5(json.dumps(filtered, sort_keys=True).encode()).hexdigest()
    secret = getattr(settings, "LEADS_SIGNING_SECRET", settings.SECRET_KEY)
    mac = hmac.new(secret.encode(), f"{timestamp}.{digest}".encode(), hashlib.sha256).hexdigest()
    return f"{timestamp}.{mac}"


class ProductLeadPolicyTests(TestCase):
    def setUp(self) -> None:
        self.collect_url = reverse("leads:collect")
        self.sign_url = reverse("leads:sign")

    def test_email_and_address_are_optional(self) -> None:
        payload = {
            "form_kind": "product_lead",
            "full_name": "Test Optional",
            "phone": "+212600000101",
        }

        sign_response = self.client.post(
            self.sign_url,
            data=json.dumps({"payload": payload}),
            content_type="application/json",
        )
        self.assertEqual(sign_response.status_code, 200)
        token = sign_response.json().get("signed_token")
        self.assertTrue(token)

        collect_body = dict(payload, signed_token=token)
        response = self.client.post(
            self.collect_url,
            data=json.dumps(collect_body),
            content_type="application/json",
            HTTP_X_IDEMPOTENCY_KEY=f"optional-{uuid4().hex}",
        )
        self.assertIn(response.status_code, {200, 202})

    def test_full_name_missing_triggers_validation_error(self) -> None:
        invalid_payload = {
            "form_kind": "product_lead",
            "phone": "+212600000202",
        }
        invalid_payload["signed_token"] = make_signed_token(invalid_payload)

        response = self.client.post(
            self.collect_url,
            data=json.dumps(invalid_payload),
            content_type="application/json",
            HTTP_X_IDEMPOTENCY_KEY=f"missing-name-{uuid4().hex}",
        )
        self.assertEqual(response.status_code, 400)
