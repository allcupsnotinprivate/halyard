"""InvocationContext: the single channel interceptors communicate through.

Interceptors never hold references to each other; everything they need to
agree on (deadline, attempt number, shared facts) travels in the context.

.. warning::
    The current-context contextvar does not survive ``run_in_executor`` or
    manually spawned threads - contextvars are copied at task creation, not
    shared. Pass the context explicitly when crossing thread boundaries.
"""

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from typing import Any

from .axes import GLOBAL_SCOPE, ScopeKey
from .clock import Clock


@dataclass(frozen=True, slots=True)
class InvocationContext:
    """Immutable description of one invocation.

    Interceptors must not mutate the context; the only mutable part is
    ``bag``, a scratch space for exchanging facts between links. A new
    attempt is a new object created via :meth:`child`.
    """

    operation: str
    correlation_id: str
    deadline: float | None = None
    attempt: int = 1
    scope_key: ScopeKey = GLOBAL_SCOPE
    #: Bound call arguments (parameter name -> value), the input a link such as
    #: cache keys on. ``None`` until a caller populates it; the mapping itself
    #: is read-only to links.
    arguments: Mapping[str, Any] | None = None
    #: Clock that interprets ``deadline``. Optional so a plain context still
    #: works, but when set it lets the base call and links read the remaining
    #: budget without threading a clock through by hand.
    clock: Clock | None = None
    bag: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def start(
        cls,
        operation: str,
        correlation_id: str,
        *,
        clock: Clock,
        budget: float | None = None,
        **fields: Any,
    ) -> "InvocationContext":
        """Build a fresh context, deriving an absolute deadline from ``budget``.

        ``budget`` is a relative number of seconds; the stored deadline is
        ``clock.monotonic() + budget``. The clock is retained so
        :meth:`remaining` and :meth:`expired` can be called without one.
        """
        deadline = None if budget is None else clock.monotonic() + budget
        return cls(operation=operation, correlation_id=correlation_id, deadline=deadline, clock=clock, **fields)

    def _clock(self, clock: Clock | None) -> Clock:
        chosen = clock if clock is not None else self.clock
        if chosen is None:
            raise ValueError("no clock available: pass one or build the context with a clock")
        return chosen

    def remaining(self, clock: Clock | None = None) -> float | None:
        """Seconds left until the deadline; ``None`` when there is no deadline.

        Uses the context's own clock when ``clock`` is omitted. Never negative:
        an expired deadline yields ``0.0``.
        """
        if self.deadline is None:
            return None
        return max(self.deadline - self._clock(clock).monotonic(), 0.0)

    def expired(self, clock: Clock | None = None) -> bool:
        """Whether the overall deadline has already passed.

        Uses the context's own clock when ``clock`` is omitted.
        """
        return self.deadline is not None and self._clock(clock).monotonic() >= self.deadline

    def child(self, **overrides: Any) -> "InvocationContext":
        """Derive a context for a new attempt (or any other override).

        ``bag`` is shared with the parent by default - it is the exchange
        channel, not per-attempt state. Override it explicitly if isolation
        is needed.
        """
        return replace(self, **overrides)


_current: ContextVar[InvocationContext | None] = ContextVar("halyard_current_context", default=None)


def current_context() -> InvocationContext | None:
    """Return the context of the invocation the caller is running inside, if any."""
    return _current.get()


@contextmanager
def use_context(ctx: InvocationContext) -> Iterator[InvocationContext]:
    """Install ``ctx`` as the current context for the duration of the block."""
    token = _current.set(ctx)
    try:
        yield ctx
    finally:
        _current.reset(token)
