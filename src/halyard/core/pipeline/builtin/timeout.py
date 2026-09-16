"""Per-attempt timeout link.

Bounds a single attempt. The effective limit is the minimum of the
configured budget and what is left of the overall deadline: the deadline
always wins. If the deadline is already exhausted, the call is not made
at all.
"""

import anyio
from pydantic import BaseModel, Field

from halyard.core.axes import EMPTY_SCOPE, ScopeKey, ScopeSpec
from halyard.core.clock import Clock
from halyard.core.context import InvocationContext
from halyard.core.errors import AttemptTimeout, DeadlineExceeded
from halyard.core.outcome import Outcome
from halyard.core.pipeline.interceptor import Interceptor, Next
from halyard.core.unit import Identity


class TimeoutSettings(BaseModel):
    """Settings of the timeout link."""

    seconds: float = Field(gt=0, description="Time budget of a single attempt, seconds")


class TimeoutInterceptor:
    """Stateless link enforcing the per-attempt budget."""

    settings_model: type[BaseModel] | None = TimeoutSettings

    def __init__(self, settings: TimeoutSettings, clock: Clock, identity: Identity | None = None) -> None:
        self.identity = identity or Identity.of("timeout")
        self._settings = settings
        self._clock = clock

    async def call(self, next: Next, ctx: InvocationContext) -> Outcome[object]:
        if ctx.expired(self._clock):
            raise DeadlineExceeded(f"deadline exhausted before attempt {ctx.attempt} of '{ctx.operation}'")

        remaining = ctx.remaining(self._clock)
        limit = self._settings.seconds if remaining is None else min(self._settings.seconds, remaining)

        with anyio.move_on_after(limit) as scope:
            return await next(ctx)
        if scope.cancelled_caught:
            raise AttemptTimeout(f"attempt {ctx.attempt} of '{ctx.operation}' exceeded {limit:.3f}s")
        raise AssertionError("unreachable")  # pragma: no cover


class TimeoutFactory:
    """Factory of the timeout link. State is empty: one instance fits all."""

    settings_model: type[BaseModel] | None = TimeoutSettings
    state_scope: ScopeSpec = EMPTY_SCOPE

    def __init__(self, settings: TimeoutSettings, clock: Clock) -> None:
        self.identity = Identity.of("timeout")
        self._settings = settings
        self._clock = clock

    def create(self, key: ScopeKey) -> Interceptor:
        return TimeoutInterceptor(self._settings, self._clock, identity=self.identity)
