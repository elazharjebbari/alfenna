from __future__ import annotations

import time
from unittest import mock

from django.test import SimpleTestCase

from apps.messaging.exceptions import TokenExpiredError
from apps.messaging.tokens import TokenService


class TokenServiceTests(SimpleTestCase):
    def test_make_and_read_roundtrip(self) -> None:
        token = TokenService.make_signed(namespace="accounts", purpose="activation", claims={"user_id": 7})
        payload = TokenService.read_signed(
            token,
            namespace="accounts",
            purpose="activation",
            ttl_seconds=60,
        )
        self.assertEqual(payload.claims["user_id"], 7)
        self.assertEqual(payload.namespace, "accounts")
        self.assertEqual(payload.purpose, "activation")

    def test_token_expiration(self) -> None:
        token = TokenService.make_signed(namespace="accounts", purpose="reset", claims={"user_id": 9})

        original_time = time.time()

        with mock.patch("django.core.signing.time.time", return_value=original_time + 120):
            with self.assertRaises(TokenExpiredError):
                TokenService.read_signed(
                    token,
                    namespace="accounts",
                    purpose="reset",
                    ttl_seconds=30,
                )
