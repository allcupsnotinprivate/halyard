"""Axis handles: a one-liner over the core axis machinery.

``App.axis`` registers a contextvar-backed axis and returns an
:class:`AxisHandle` to bind its value per request/task::

    tenant = app.axis("tenant", default="public")
    with tenant.use("acme"):
        ...  # scoped components and [tenant]-sliced state resolve to "acme"
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar


class AxisHandle:
    """A bound axis: set its value for a block, or read the current one."""

    def __init__(self, name: str, var: ContextVar[str | None]) -> None:
        self.name = name
        self._var = var

    @contextmanager
    def use(self, value: str) -> Iterator[str]:
        """Bind ``value`` for the axis inside the block."""
        token = self._var.set(value)
        try:
            yield value
        finally:
            self._var.reset(token)

    def current(self) -> str | None:
        """The axis's current value, if bound."""
        return self._var.get()
