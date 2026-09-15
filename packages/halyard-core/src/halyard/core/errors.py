"""Error taxonomy and pluggable error classification.

The taxonomy is the foundation for retry (and, later, circuit breaking):
interceptors must be able to tell "the service is down" from "the key is
wrong" without knowing anything about the caller's domain.
"""

from enum import StrEnum
from typing import Protocol


class FrameworkError(Exception):
    """Base class for all framework errors."""


class TransientError(FrameworkError):
    """Temporary failure; retrying makes sense (network blip, 5xx, call timeout)."""


class PermanentError(FrameworkError):
    """Retrying is pointless (4xx, invalid configuration, validation failure)."""


class ConfigurationError(PermanentError):
    """Invalid configuration; handled at startup, never retried."""


class DeadlineExceeded(TransientError):
    """Overall deadline for the invocation is exhausted."""


class AttemptTimeout(TransientError):
    """A single attempt ran out of its per-attempt time budget."""


class RetryExhausted(TransientError):
    """Every retry attempt was spent; wraps the last underlying failure.

    Raised by the retry link when a retryable call keeps failing until the
    attempt budget is used up. The original exception is preserved both as
    ``__cause__`` and on ``last_error`` so callers can catch a single
    framework type instead of every client library's exception.
    """

    def __init__(self, message: str, *, attempts: int, last_error: BaseException) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.last_error = last_error


class ErrorClass(StrEnum):
    """Classification verdict used by retry (and future circuit breaker)."""

    TRANSIENT = "transient"
    PERMANENT = "permanent"


class ErrorClassifier(Protocol):
    """Pluggable classification of arbitrary exceptions.

    Classification of third-party exceptions is deliberately external to the
    taxonomy: applications map their client-library errors here instead of
    wrapping every call site.
    """

    def classify(self, exc: BaseException) -> ErrorClass:
        """Return the error class for ``exc``."""
        ...


class DefaultErrorClassifier:
    """Classify by the framework taxonomy only.

    Unknown exceptions are ``PERMANENT`` by design: treating anything
    unfamiliar as transient would mean retrying bugs in code.
    """

    def classify(self, exc: BaseException) -> ErrorClass:
        if isinstance(exc, TransientError):
            return ErrorClass.TRANSIENT
        return ErrorClass.PERMANENT
