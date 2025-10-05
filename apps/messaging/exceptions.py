"""Custom exceptions for the messaging domain."""
from __future__ import annotations


class MessagingError(Exception):
    """Base class for messaging domain errors."""


class TokenExpiredError(MessagingError):
    """Raised when a signed token expired before use."""


class TokenInvalidError(MessagingError):
    """Raised when a signed token payload cannot be trusted."""


class TemplateNotFoundError(MessagingError):
    """Raised when no active template can be resolved for a slug/locale pair."""


class DeduplicationConflictError(MessagingError):
    """Raised when attempting to enqueue an e-mail that already exists."""
