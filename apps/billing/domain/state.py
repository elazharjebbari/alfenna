from __future__ import annotations

from enum import Enum
from typing import Dict, Mapping, Set

from apps.billing.models import OrderStatus

from .errors import InvalidTransition


class OrderEvent(str, Enum):
    """Events that can mutate an order."""

    CHECKOUT_CREATED = "checkout_created"
    PAYMENT_REQUIRES_ACTION = "payment_requires_action"
    PAYMENT_SUCCEEDED = "payment_succeeded"
    PAYMENT_FAILED = "payment_failed"
    CANCELLED = "cancelled"
    REFUND_REQUESTED = "refund_requested"
    REFUND_SUCCEEDED = "refund_succeeded"
    REFUND_FAILED = "refund_failed"


_TRANSITIONS: Mapping[OrderStatus, Dict[OrderEvent, OrderStatus]] = {
    OrderStatus.DRAFT: {
        OrderEvent.CHECKOUT_CREATED: OrderStatus.PENDING_PAYMENT,
        OrderEvent.CANCELLED: OrderStatus.CANCELED,
    },
    OrderStatus.PENDING_PAYMENT: {
        OrderEvent.PAYMENT_REQUIRES_ACTION: OrderStatus.REQUIRES_ACTION,
        OrderEvent.PAYMENT_SUCCEEDED: OrderStatus.PAID,
        OrderEvent.PAYMENT_FAILED: OrderStatus.CANCELED,
        OrderEvent.CANCELLED: OrderStatus.CANCELED,
    },
    OrderStatus.REQUIRES_ACTION: {
        OrderEvent.PAYMENT_SUCCEEDED: OrderStatus.PAID,
        OrderEvent.PAYMENT_FAILED: OrderStatus.CANCELED,
        OrderEvent.CANCELLED: OrderStatus.CANCELED,
    },
    OrderStatus.PAID: {
        OrderEvent.REFUND_REQUESTED: OrderStatus.PAID,
        OrderEvent.REFUND_SUCCEEDED: OrderStatus.REFUNDED,
        OrderEvent.CANCELLED: OrderStatus.CANCELED,
    },
    OrderStatus.CANCELED: {
        OrderEvent.REFUND_REQUESTED: OrderStatus.CANCELED,
        OrderEvent.REFUND_SUCCEEDED: OrderStatus.REFUNDED,
    },
    OrderStatus.REFUNDED: {
        OrderEvent.REFUND_REQUESTED: OrderStatus.REFUNDED,
        OrderEvent.REFUND_SUCCEEDED: OrderStatus.REFUNDED,
    },
}


_IDEMPOTENT: Mapping[OrderEvent, Set[OrderStatus]] = {
    OrderEvent.PAYMENT_SUCCEEDED: {OrderStatus.PAID, OrderStatus.REFUNDED},
    OrderEvent.PAYMENT_REQUIRES_ACTION: {OrderStatus.REQUIRES_ACTION},
    OrderEvent.PAYMENT_FAILED: {OrderStatus.CANCELED},
    OrderEvent.CANCELLED: {OrderStatus.CANCELED},
    OrderEvent.REFUND_SUCCEEDED: {OrderStatus.REFUNDED},
    OrderEvent.REFUND_REQUESTED: {OrderStatus.REFUNDED, OrderStatus.CANCELED, OrderStatus.PAID},
}


def is_allowed(current: OrderStatus, event: OrderEvent) -> bool:
    """Return True if the transition is defined."""

    if event in _IDEMPOTENT and current in _IDEMPOTENT[event]:
        return True
    return event in _TRANSITIONS.get(current, {})


def transition(current: OrderStatus, event: OrderEvent) -> OrderStatus:
    """Return the next state or raise InvalidTransition."""

    if event in _IDEMPOTENT and current in _IDEMPOTENT[event]:
        return current

    try:
        return _TRANSITIONS[current][event]
    except KeyError as exc:  # pragma: no cover - trivial mapping guard
        raise InvalidTransition(current=current, event=event.value) from exc


def allowed_events(current: OrderStatus) -> Set[OrderEvent]:
    """Possible events from current state."""

    events = set(_TRANSITIONS.get(current, {}).keys())
    for event, states in _IDEMPOTENT.items():
        if current in states:
            events.add(event)
    return events
