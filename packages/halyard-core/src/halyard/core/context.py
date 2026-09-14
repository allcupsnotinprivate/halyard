"""InvocationContext: the single channel interceptors communicate through.

Interceptors never hold references to each other; everything they need to
agree on (deadline, attempt number, shared facts) travels in the context.

.. warning::
    The current-context contextvar does not survive ``run_in_executor`` or
    manually spawned threads - contextvars are copied at task creation, not
    shared. Pass the context explicitly when crossing thread boundaries.
"""

from collections.abc import Iterator
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
    bag: dict[str, Any] = field(default_factory=dict)

    def remaining(self, clock: Clock) -> float | None:
        """Seconds left until the deadline; ``None`` when there is no deadline.

        Never negative: an expired deadline yields ``0.0``.
        """
        if self.deadline is None:
            return None
        return max(self.deadline - clock.monotonic(), 0.0)

    def expired(self, clock: Clock) -> bool:
        """Whether the overall deadline has already passed."""
        return self.deadline is not None and clock.monotonic() >= self.deadline

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
