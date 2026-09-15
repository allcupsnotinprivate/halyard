"""Wrap a *real* HTTP integration in the pipeline, by hand.

No ``AComponent``, no registry, no container - just the core primitives
composed manually around a live ``httpx`` call. The point is not to ship
this code; it is to find out, on a real call, whether ``InvocationContext``
carries everything the base call and the links need, and how much glue a
plain integration still has to write.

Run (needs outbound network to httpbin.org):
    uv run python examples/httpx_manual_pipeline.py

Override the target if httpbin is unavailable:
    HALYARD_GATE_BASE=https://your-httpbin uv run python examples/httpx_manual_pipeline.py
"""

from __future__ import annotations

import os
from typing import Any
import uuid

import anyio
import httpx

from halyard.core.axes import AxisRegistry
from halyard.core.clock import SystemClock
from halyard.core.context import InvocationContext
from halyard.core.errors import (
    AttemptTimeout,
    ErrorClass,
    PermanentError,
    TransientError,
)
from halyard.core.outcome import Outcome
from halyard.core.pipeline.builtin.retry import RetryFactory, RetrySettings
from halyard.core.pipeline.builtin.timeout import TimeoutFactory, TimeoutSettings
from halyard.core.pipeline.chain import build_chain
from halyard.core.pipeline.state import InMemoryStateStore

BASE = os.environ.get("HALYARD_GATE_BASE", "https://httpbin.org")


# --- glue #1: map a third-party client's exceptions onto the taxonomy --------
# The default classifier calls every unknown exception PERMANENT, so a bare
# httpx error would never be retried. Every real integration must write this.
class HttpxErrorClassifier:
    """Classify httpx failures: 5xx / network / timeout are transient, 4xx not."""

    def classify(self, exc: BaseException) -> ErrorClass:
        if isinstance(exc, TransientError):
            return ErrorClass.TRANSIENT
        if isinstance(exc, httpx.HTTPStatusError):
            code = exc.response.status_code
            return ErrorClass.TRANSIENT if code >= 500 else ErrorClass.PERMANENT
        if isinstance(exc, httpx.TimeoutException | httpx.TransportError):
            return ErrorClass.TRANSIENT
        return ErrorClass.PERMANENT


# --- glue #2: adapt a real call to the Next signature ------------------------
# The base call receives only ``ctx``. The URL and http client are still
# threaded in by closure, but the clock rides in the context now, so the
# remaining deadline is read straight off ``ctx``.
def make_http_get(client: httpx.AsyncClient, path: str) -> Any:
    async def call(ctx: InvocationContext) -> Outcome[dict[str, Any]]:
        remaining = ctx.remaining()
        timeout = 30.0 if remaining is None else max(0.001, remaining)
        try:
            resp = await client.get(
                f"{BASE}{path}",
                # correlation_id earns its keep: it rides out on the wire.
                headers={"X-Correlation-Id": ctx.correlation_id},
                timeout=timeout,
            )
            resp.raise_for_status()
        except httpx.TimeoutException as exc:
            # Surface as the taxonomy's attempt-timeout so links understand it.
            raise AttemptTimeout(f"http get {path} timed out") from exc
        except httpx.HTTPStatusError:
            raise  # classified by HttpxErrorClassifier
        return Outcome(value={"status": resp.status_code, "len": len(resp.content)})

    return call


async def run(label: str, chain: Any, ctx: InvocationContext) -> None:
    print(f"\n=== {label} (correlation_id={ctx.correlation_id}) ===")
    try:
        outcome = await chain(ctx)
        print(f"  OK    value={outcome.value} attempts={outcome.attempts} elapsed={outcome.elapsed:.3f}s")
    except (TransientError, PermanentError) as exc:
        # Exhausted retries now surface as RetryExhausted (a framework error)
        # wrapping the last httpx failure, so catching FrameworkError is enough.
        cause = f" (cause: {type(exc.__cause__).__name__})" if exc.__cause__ else ""
        print(f"  FAIL  (framework) {type(exc).__name__}: {exc}{cause}")


async def main() -> None:
    clock = SystemClock()
    classifier = HttpxErrorClassifier()

    def chain_for(path: str, *, attempts: int, per_attempt: float) -> Any:
        retry = RetryFactory(
            RetrySettings(attempts=attempts, base_delay=0.1, max_delay=1.0, jitter=True),
            clock,
            classifier=classifier,
        )
        timeout = TimeoutFactory(TimeoutSettings(seconds=per_attempt), clock)
        base = make_http_get(client, path)
        return build_chain([retry, timeout], InMemoryStateStore(), AxisRegistry(), base)

    def start(operation: str, budget: float) -> InvocationContext:
        return InvocationContext.start(operation, uuid.uuid4().hex[:8], clock=clock, budget=budget)

    async with httpx.AsyncClient() as client:
        # 1. Happy path: a real 200, single attempt.
        await run(
            "happy path GET /get",
            chain_for("/get", attempts=3, per_attempt=5.0),
            start("httpbin.get", budget=10.0),
        )

        # 2. Real 503 -> classified transient -> retried -> deadline cuts it.
        await run(
            "transient 503, deadline-bounded",
            chain_for("/status/503", attempts=5, per_attempt=5.0),
            start("httpbin.boom", budget=2.0),
        )

        # 3. Real slow endpoint -> per-attempt timeout -> retried -> deadline.
        await run(
            "slow /delay/10, per-attempt 1s",
            chain_for("/delay/10", attempts=5, per_attempt=1.0),
            start("httpbin.slow", budget=3.0),
        )


if __name__ == "__main__":
    anyio.run(main)
