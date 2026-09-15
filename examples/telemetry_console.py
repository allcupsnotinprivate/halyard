"""Runnable demo: the same retry+timeout chain, instrumented to the console.

Same flaky service as ``retry_timeout.py``, wrapped with
``halyard.core.telemetry.instrument`` and explicit SDK providers that print
spans and metrics to stdout. Watch for: one invocation span, three
``halyard.attempt`` child spans (the first two failed), a backoff event, and
the ``halyard.calls`` / ``halyard.call.duration`` metrics.

Without the SDK configured, the very same ``instrument()`` call is a no-op -
that is the whole point: instrumentation is always on, collection is the
application's choice.

Run:
    uv run python examples/telemetry_console.py
"""

import anyio
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

from halyard.core.axes import AxisRegistry
from halyard.core.clock import SystemClock
from halyard.core.context import InvocationContext
from halyard.core.errors import TransientError
from halyard.core.outcome import Outcome
from halyard.core.pipeline.builtin.retry import RetryFactory, RetrySettings
from halyard.core.pipeline.builtin.timeout import TimeoutFactory, TimeoutSettings
from halyard.core.pipeline.chain import build_chain
from halyard.core.pipeline.state import InMemoryStateStore
from halyard.core.telemetry.instrument import instrument

SCRIPT = ["network-error", "hang", "ok"]
calls = 0


async def flaky_service(ctx: InvocationContext) -> Outcome[str]:
    """Pretends to be a remote service with a bad day."""
    global calls
    action = SCRIPT[calls] if calls < len(SCRIPT) else "ok"
    calls += 1

    if action == "network-error":
        raise TransientError("connection reset by peer")
    if action == "hang":
        await anyio.sleep(3600)  # the timeout link will cut this attempt
    return Outcome(value=f"payload (delivered on attempt {ctx.attempt})")


async def main() -> None:
    # Explicit SDK providers printing to the console; a real app would export
    # to a collector instead and typically set the OTel globals once.
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    meter_provider = MeterProvider(
        metric_readers=[PeriodicExportingMetricReader(ConsoleMetricExporter(), export_interval_millis=60_000)]
    )

    clock = SystemClock()
    retry = RetryFactory(RetrySettings(attempts=5, base_delay=0.05, max_delay=0.4), clock)
    timeout = TimeoutFactory(TimeoutSettings(seconds=0.2), clock)
    chain = build_chain([retry, timeout], InMemoryStateStore(), AxisRegistry(), flaky_service)

    wrapped = instrument(chain, tracer_provider=tracer_provider, meter_provider=meter_provider, clock=clock)

    ctx = InvocationContext.start("demo.fetch", "example-telemetry", clock=clock, budget=5.0)
    outcome = await wrapped(ctx)
    print(f"\nresult: {outcome.value!r} (attempts={outcome.attempts}, elapsed={outcome.elapsed:.3f}s)\n")

    meter_provider.shutdown()  # flush the metrics to the console
    tracer_provider.shutdown()


if __name__ == "__main__":
    anyio.run(main)
