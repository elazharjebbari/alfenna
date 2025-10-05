from __future__ import annotations


class BillingDomainError(Exception):
    """Base error for the billing domain layer."""


class InvalidTransition(BillingDomainError):
    """Raised when an order transition is not allowed."""

    def __init__(self, current: str, event: str) -> None:
        super().__init__(f"Transition '{event}' not allowed from state '{current}'")
        self.current = current
        self.event = event
