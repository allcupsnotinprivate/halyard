"""Runnable demo: a timeout link inside a retry link around a misbehaving call.

The fake service follows a script:
  attempt 1 - fails with a transient network error,
  attempt 2 - hangs (the timeout link cuts it),
  attempt 3 - succeeds.

Run:
    uv run python examples/retry_timeout.py
"""

import anyio

from halyard.core.axes import AxisRegistry
from halyard.core.clock import SystemClock
from halyard.core.context import InvocationContext
from halyard.core.errors import TransientError
from halyard.core.outcome import Outcome
from halyard.core.pipeline.builtin.retry import RetryFactory, RetrySettings
from halyard.core.pipeline.builtin.timeout import TimeoutFactory, TimeoutSettings
from halyard.core.pipeline.chain import build_chain
from halyard.core.pipeline.state import InMemoryStateStore

SCRIPT = ["network-error", "hang", "ok"]
calls = 0


async def flaky_service(ctx: InvocationContext) -> Outcome[str]:
    """Pretends to be a remote service with a bad day."""
    global calls
    action = SCRIPT[calls] if calls < len(SCRIPT) else "ok"
    calls += 1
    print(f"  attempt {ctx.attempt}: service does '{action}'")

    if action == "network-error":
        raise TransientError("connection reset by peer")
    if action == "hang":
        await anyio.sleep(3600)  # the timeout link will cut this attempt
    return Outcome(value=f"payload (delivered on attempt {ctx.attempt})")


async def main() -> None:
    clock = SystemClock()

    retry = RetryFactory(
        RetrySettings(attempts=5, base_delay=0.05, max_delay=0.4, jitter=True),
        clock,
    )
    timeout = TimeoutFactory(TimeoutSettings(seconds=0.2), clock)

    # First in the list is the outermost link: retry wraps timeout wraps the call.
    chain = build_chain([retry, timeout], InMemoryStateStore(), AxisRegistry(), flaky_service)

    ctx = InvocationContext(
        operation="demo.fetch",
        correlation_id="example-1",
        deadline=clock.monotonic() + 5.0,
    )

    print(f"calling '{ctx.operation}' (retry: 5 attempts, timeout: 0.2s/attempt, deadline: 5s)")
    outcome = await chain(ctx)
    print("result:")
    print(f"  value    = {outcome.value!r}")
    print(f"  source   = {outcome.source}")
    print(f"  degraded = {outcome.degraded}")
    print(f"  attempts = {outcome.attempts}")
    print(f"  elapsed  = {outcome.elapsed:.3f}s")


if __name__ == "__main__":
    anyio.run(main)
