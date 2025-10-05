from django.test import SimpleTestCase

from apps.billing.domain import state
from apps.billing.domain.errors import InvalidTransition
from apps.billing.models import OrderStatus


class OrderStateMachineTests(SimpleTestCase):
    def test_valid_transition_sequence(self) -> None:
        current = OrderStatus.DRAFT
        current = state.transition(current, state.OrderEvent.CHECKOUT_CREATED)
        self.assertEqual(current, OrderStatus.PENDING_PAYMENT)
        current = state.transition(current, state.OrderEvent.PAYMENT_SUCCEEDED)
        self.assertEqual(current, OrderStatus.PAID)
        current = state.transition(current, state.OrderEvent.REFUND_SUCCEEDED)
        self.assertEqual(current, OrderStatus.REFUNDED)

    def test_idempotent_event_does_not_change_state(self) -> None:
        current = OrderStatus.PAID
        next_state = state.transition(current, state.OrderEvent.PAYMENT_SUCCEEDED)
        self.assertEqual(next_state, OrderStatus.PAID)

    def test_invalid_transition_raises(self) -> None:
        with self.assertRaises(InvalidTransition):
            state.transition(OrderStatus.DRAFT, state.OrderEvent.PAYMENT_SUCCEEDED)

    def test_allowed_events_listing(self) -> None:
        events = state.allowed_events(OrderStatus.PENDING_PAYMENT)
        self.assertIn(state.OrderEvent.PAYMENT_SUCCEEDED, events)
        self.assertIn(state.OrderEvent.PAYMENT_FAILED, events)
        self.assertIn(state.OrderEvent.CANCELLED, events)
