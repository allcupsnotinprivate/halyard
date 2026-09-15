"""Retry link: exponential backoff with full jitter, deadline-aware.

The most safety-critical rule lives here: before every new attempt the
overall deadline is checked, and if the pause before the next attempt does
not fit into what remains, the link gives up immediately with
DeadlineExceeded instead of making the caller wait beyond its budget.
"""

from dataclasses import replace
import random

from pydantic import BaseModel, Field, model_validator

from halyard.core.axes import EMPTY_SCOPE, ScopeKey, ScopeSpec
from halyard.core.clock import Clock
from halyard.core.context import InvocationContext
from halyard.core.errors import (
    DeadlineExceeded,
    DefaultErrorClassifier,
    ErrorClass,
    ErrorClassifier,
    RetryExhausted,
)
from halyard.core.outcome import Outcome
from halyard.core.pipeline.interceptor import Interceptor, Next
from halyard.core.unit import Identity


class RetrySettings(BaseModel):
    """Settings of the retry link."""

    attempts: int = Field(ge=1, description="Maximum number of attempts, including the first one")
    base_delay: float = Field(ge=0, description="Backoff base, seconds")
    max_delay: float = Field(gt=0, description="Backoff cap, seconds")
    jitter: bool = Field(default=True, description="Full jitter: sleep uniform(0, delay) instead of delay")
    retry_on: ErrorClass = Field(default=ErrorClass.TRANSIENT, description="Error class worth retrying")

    @model_validator(mode="after")
    def _cap_not_below_base(self) -> "RetrySettings":
        if self.max_delay < self.base_delay:
            raise ValueError("max_delay must not be below base_delay")
        return self


class RetryInterceptor:
    """Repeats the wrapped call while the classifier deems failures retryable."""

    settings_model: type[BaseModel] | None = RetrySettings

    def __init__(
        self,
        settings: RetrySettings,
        clock: Clock,
        classifier: ErrorClassifier | None = None,
        rng: random.Random | None = None,
        identity: Identity | None = None,
    ) -> None:
        self.identity = identity or Identity.of("retry")
        self._settings = settings
        self._clock = clock
        self._classifier = classifier or DefaultErrorClassifier()
        # Not cryptographic: jitter only needs to desynchronize clients.
        self._rng = rng or random.Random()  # noqa: S311

    def _delay_before(self, next_attempt: int) -> float:
        """Backoff before attempt ``next_attempt`` (attempt numbering starts at 1)."""
        exponent = next_attempt - 2  # first retry (attempt 2) sleeps ~base_delay
        delay = min(self._settings.base_delay * (2.0**exponent), self._settings.max_delay)
        if self._settings.jitter:
            delay = self._rng.uniform(0.0, delay)
        return delay

    async def call(self, next: Next, ctx: InvocationContext) -> Outcome[object]:
        started = self._clock.monotonic()

        for attempt in range(1, self._settings.attempts + 1):
            if ctx.expired(self._clock):
                raise DeadlineExceeded(f"deadline exhausted before attempt {attempt} of '{ctx.operation}'")

            attempt_ctx = ctx.child(attempt=attempt)
            try:
                outcome = await next(attempt_ctx)
            except Exception as exc:
                if self._classifier.classify(exc) != self._settings.retry_on:
                    raise
                if attempt == self._settings.attempts:
                    # Retryable, but the attempt budget is spent: surface a
                    # framework error wrapping the last failure, so the caller
                    # never has to catch the client library's own exception.
                    raise RetryExhausted(
                        f"'{ctx.operation}' exhausted after {attempt} attempts: {exc}",
                        attempts=attempt,
                        last_error=exc,
                    ) from exc

                delay = self._delay_before(attempt + 1)
                remaining = ctx.remaining(self._clock)
                if remaining is not None and delay >= remaining:
                    # The pause alone would eat the rest of the budget:
                    # do not sleep, do not try - fail fast.
                    raise DeadlineExceeded(
                        f"retry of '{ctx.operation}' abandoned: backoff {delay:.3f}s exceeds remaining {remaining:.3f}s"
                    ) from exc
                await self._clock.sleep(delay)
            else:
                return replace(
                    outcome,
                    attempts=attempt,
                    elapsed=self._clock.monotonic() - started,
                )

        raise AssertionError("unreachable")  # pragma: no cover


class RetryFactory:
    """Factory of the retry link. State is empty: the link is per-call stateless."""

    settings_model: type[BaseModel] | None = RetrySettings
    state_scope: ScopeSpec = EMPTY_SCOPE

    def __init__(
        self,
        settings: RetrySettings,
        clock: Clock,
        classifier: ErrorClassifier | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self.identity = Identity.of("retry")
        self._settings = settings
        self._clock = clock
        self._classifier = classifier
        self._rng = rng

    def create(self, key: ScopeKey) -> Interceptor:
        return RetryInterceptor(self._settings, self._clock, self._classifier, self._rng, identity=self.identity)
