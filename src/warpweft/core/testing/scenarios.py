"""Scripted base calls for exercising a policy chain.

Each returns a ``Next`` - a base call the chain wraps - following a failure
script. Feed one to `warpweft.core.testing.drive_policy`, or model a fake
dependency with it.
"""

import anyio

from warpweft.core.context import InvocationContext
from warpweft.core.errors import AttemptTimeout, PermanentError, TransientError
from warpweft.core.outcome import Outcome
from warpweft.core.pipeline.interceptor import Next


def fails_then_succeeds(failures: int, value: object = "ok", *, error: type[Exception] = TransientError) -> Next:
    """Fail ``failures`` times (transient by default), then return ``value``."""
    calls = 0

    async def base(ctx: InvocationContext) -> Outcome[object]:
        nonlocal calls
        calls += 1
        if calls <= failures:
            raise error(f"scripted failure {calls}/{failures}")
        return Outcome(value=value)

    return base


def always_transient(message: str = "scripted transient failure") -> Next:
    """Always raise a transient error (retryable)."""

    async def base(ctx: InvocationContext) -> Outcome[object]:
        raise TransientError(message)

    return base


def always_permanent(message: str = "scripted permanent failure") -> Next:
    """Always raise a permanent error (not retryable)."""

    async def base(ctx: InvocationContext) -> Outcome[object]:
        raise PermanentError(message)

    return base


def always_times_out(message: str = "scripted attempt timeout") -> Next:
    """Always raise an attempt timeout (transient) - instant, no real waiting."""

    async def base(ctx: InvocationContext) -> Outcome[object]:
        raise AttemptTimeout(message)

    return base


def hangs() -> Next:
    """Never return. Use with a small ``timeout`` to exercise the timeout link.

    Unlike `always_times_out`, this really blocks, so the enclosing
    ``timeout`` link must cut it - which uses real time. Keep the configured
    ``seconds`` small.
    """

    async def base(ctx: InvocationContext) -> Outcome[object]:
        await anyio.sleep_forever()
        raise AssertionError("unreachable")  # pragma: no cover

    return base
