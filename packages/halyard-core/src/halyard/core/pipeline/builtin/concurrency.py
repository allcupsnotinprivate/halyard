"""Concurrency link: two-level admission control, deadline-aware.

Two limits act at once:

- an **outer** semaphore per ``[endpoint]`` - protects the capacity of the
  receiving side; every caller of one endpoint shares it;
- an **inner** semaphore per instance slice - gives each caller a fair share so
  one aggressive source cannot starve the others.

Acquisition order is **inner first, then outer**, always. The reverse order
would let one source queue up the whole outer semaphore and crowd everyone out;
a single consistent order is also what guarantees freedom from deadlock.

Waiting respects the context deadline: if the budget is already gone the slot
is not requested, and a wait that would outlast the budget ends in
``DeadlineExceeded`` rather than blocking past it.
"""

import anyio
from pydantic import BaseModel, Field

from halyard.core.axes import ScopeKey, ScopeSpec
from halyard.core.clock import Clock
from halyard.core.context import InvocationContext
from halyard.core.errors import DeadlineExceeded
from halyard.core.outcome import Outcome
from halyard.core.pipeline.interceptor import Interceptor, Next
from halyard.core.unit import Identity

#: The outer semaphore is sliced per endpoint. The axis is registered where the
#: pipeline meets components; the slice is declared here.
ENDPOINT_SCOPE = ScopeSpec(("endpoint",))


class ConcurrencySettings(BaseModel):
    """Settings of the concurrency link."""

    inner_limit: int = Field(ge=1, description="Concurrent calls allowed per instance slice (fair share)")
    outer_limit: int = Field(ge=1, description="Concurrent calls allowed per endpoint (receiver capacity)")


class ConcurrencyInterceptor:
    """One instance per endpoint: owns the outer semaphore, one inner per slice."""

    settings_model: type[BaseModel] | None = ConcurrencySettings

    def __init__(self, settings: ConcurrencySettings, clock: Clock, identity: Identity | None = None) -> None:
        self.identity = identity or Identity.of("concurrency")
        self._settings = settings
        self._clock = clock
        self._outer = anyio.Semaphore(settings.outer_limit)
        # Inner semaphores are created lazily per invocation slice. The map may
        # grow with the number of live slices; eviction is the state store's job
        # once the pipeline is wired to instances.
        self._inner: dict[ScopeKey, anyio.Semaphore] = {}

    @property
    def outer_limit(self) -> int:
        """Configured endpoint-wide concurrency cap (for introspection)."""
        return self._settings.outer_limit

    @property
    def outer_available(self) -> int:
        """Free slots on the endpoint-wide semaphore right now."""
        return self._outer.value

    @property
    def inner_slice_count(self) -> int:
        """Number of instance slices with a live inner semaphore."""
        return len(self._inner)

    def _inner_for(self, key: ScopeKey) -> anyio.Semaphore:
        sem = self._inner.get(key)
        if sem is None:  # no await between get and set: safe without a lock
            sem = anyio.Semaphore(self._settings.inner_limit)
            self._inner[key] = sem
        return sem

    async def _acquire(self, sem: anyio.Semaphore, ctx: InvocationContext, level: str) -> None:
        if ctx.expired(self._clock):
            raise DeadlineExceeded(f"deadline exhausted before acquiring {level} slot for '{ctx.operation}'")
        remaining = ctx.remaining(self._clock)
        if remaining is None:
            await sem.acquire()
            return
        with anyio.move_on_after(remaining) as scope:
            await sem.acquire()
        if scope.cancelled_caught:
            raise DeadlineExceeded(f"waiting for {level} slot for '{ctx.operation}' would exceed the deadline")

    async def call(self, next: Next, ctx: InvocationContext) -> Outcome[object]:
        inner = self._inner_for(ctx.scope_key)
        await self._acquire(inner, ctx, "inner")
        try:
            await self._acquire(self._outer, ctx, "outer")
            try:
                return await next(ctx)
            finally:
                self._outer.release()
        finally:
            inner.release()


class ConcurrencyFactory:
    """Factory of the concurrency link. One instance per endpoint slice."""

    settings_model: type[BaseModel] | None = ConcurrencySettings
    state_scope: ScopeSpec = ENDPOINT_SCOPE

    def __init__(self, settings: ConcurrencySettings, clock: Clock) -> None:
        self.identity = Identity.of("concurrency")
        self._settings = settings
        self._clock = clock

    def create(self, key: ScopeKey) -> Interceptor:
        return ConcurrencyInterceptor(self._settings, self._clock, identity=self.identity)
