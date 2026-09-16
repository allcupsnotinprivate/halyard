"""The built-in ``endpoint`` axis.

Unlike an ordinary axis, ``endpoint`` does not read a request-scoped value: it
reflects which external system the *current instance* talks to. The container
sets it around each invocation from the instance's :meth:`AComponent.endpoint`,
so ``[endpoint]``-sliced link state (breaker, concurrency) is shared by all
instances hitting the same endpoint and separated otherwise - without any
component declaring it.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from halyard.core.axes import Axis

#: Name of the built-in endpoint axis.
ENDPOINT_AXIS = "endpoint"

_current_endpoint: ContextVar[str | None] = ContextVar("halyard_current_endpoint", default=None)


@contextmanager
def use_endpoint(value: str) -> Iterator[None]:
    """Bind the current endpoint for the duration of an invocation."""
    token = _current_endpoint.set(value)
    try:
        yield
    finally:
        _current_endpoint.reset(token)


def endpoint_axis() -> Axis:
    """The endpoint axis: resolves to the endpoint bound by :func:`use_endpoint`."""
    return Axis(name=ENDPOINT_AXIS, resolver=_current_endpoint.get)
