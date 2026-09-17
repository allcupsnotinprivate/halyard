"""Circuit breaker: window-based tripping, half-open probing, transient-only.

No test sleeps for real: ManualClock drives the reset timeout.
"""

import contextlib
from typing import Any

import anyio
from pydantic import ValidationError
import pytest

from warpweft.core.clock import ManualClock
from warpweft.core.context import InvocationContext
from warpweft.core.errors import CircuitOpen, PermanentError, TransientError
from warpweft.core.outcome import Outcome
from warpweft.core.pipeline.builtin.circuit_breaker import (
    ENDPOINT_SCOPE,
    CircuitBreakerFactory,
    CircuitBreakerInterceptor,
    CircuitBreakerSettings,
    CircuitState,
)
from warpweft.core.pipeline.interceptor import Next

pytestmark = [pytest.mark.unit, pytest.mark.anyio]


class Call:
    """Base call driven by a script of actions, counting how often it ran."""

    def __init__(self, action: str = "ok") -> None:
        self.action = action
        self.calls = 0

    async def __call__(self, ctx: InvocationContext) -> Outcome[Any]:
        self.calls += 1
        if self.action == "ok":
            return Outcome(value="ok")
        if self.action == "transient":
            raise TransientError("boom")
        if self.action == "permanent":
            raise PermanentError("nope")
        raise AssertionError(self.action)


def breaker(
    clock: Any, *, window: int = 3, failure_threshold: int = 3, reset_timeout: float = 10.0
) -> CircuitBreakerInterceptor:
    settings = CircuitBreakerSettings(window=window, failure_threshold=failure_threshold, reset_timeout=reset_timeout)
    return CircuitBreakerInterceptor(settings, clock)


def ctx(**overrides: Any) -> InvocationContext:
    defaults: dict[str, Any] = {"operation": "op", "correlation_id": "cid"}
    defaults.update(overrides)
    return InvocationContext(**defaults)


async def test_closed_passes_success_through() -> None:
    cb = breaker(ManualClock())
    outcome = await cb.call(Call("ok"), ctx())
    assert outcome.value == "ok"
    assert cb.state is CircuitState.CLOSED


async def test_opens_after_threshold_transient_failures() -> None:
    cb = breaker(ManualClock(), window=3, failure_threshold=3)
    call = Call("transient")
    for _ in range(3):
        with pytest.raises(TransientError):
            await cb.call(call, ctx())
    assert cb.state is CircuitState.OPEN


async def test_open_rejects_without_calling_next() -> None:
    cb = breaker(ManualClock(), window=2, failure_threshold=2)
    fail = Call("transient")
    for _ in range(2):
        with pytest.raises(TransientError):
            await cb.call(fail, ctx())
    assert cb.state is CircuitState.OPEN

    probe = Call("ok")
    with pytest.raises(CircuitOpen):
        await cb.call(probe, ctx())
    assert probe.calls == 0  # the call never reached the base


async def test_open_rejection_reports_time_until_probe() -> None:
    clock = ManualClock()
    cb = breaker(clock, window=2, failure_threshold=2, reset_timeout=10.0)
    fail = Call("transient")
    for _ in range(2):
        with pytest.raises(TransientError):
            await cb.call(fail, ctx())

    clock.advance(4.0)
    with pytest.raises(CircuitOpen) as info:
        await cb.call(Call("ok"), ctx())
    assert info.value.retry_after == pytest.approx(6.0)


async def test_permanent_errors_do_not_open_the_breaker() -> None:
    cb = breaker(ManualClock(), window=3, failure_threshold=2)
    call = Call("permanent")
    for _ in range(5):
        with pytest.raises(PermanentError):
            await cb.call(call, ctx())
    assert cb.state is CircuitState.CLOSED


async def test_sliding_window_forgets_old_failures() -> None:
    cb = breaker(ManualClock(), window=3, failure_threshold=3)
    fail, ok = Call("transient"), Call("ok")

    # F, F, S, F -> the window is [F, S, F], only 2 failures: never trips.
    for action in (fail, fail, ok, fail):
        with contextlib.suppress(TransientError):
            await cb.call(action, ctx())
    assert cb.state is CircuitState.CLOSED


async def test_half_open_after_reset_lets_one_probe_and_closes_on_success() -> None:
    clock = ManualClock()
    cb = breaker(clock, window=2, failure_threshold=2, reset_timeout=10.0)
    for _ in range(2):
        with pytest.raises(TransientError):
            await cb.call(Call("transient"), ctx())
    assert cb.state is CircuitState.OPEN

    clock.advance(10.0)  # reset elapsed -> next call is the probe
    probe = Call("ok")
    outcome = await cb.call(probe, ctx())
    assert outcome.value == "ok"
    assert probe.calls == 1
    assert cb.state is CircuitState.CLOSED


async def test_half_open_probe_failure_reopens() -> None:
    clock = ManualClock()
    cb = breaker(clock, window=1, failure_threshold=1, reset_timeout=5.0)
    with pytest.raises(TransientError):
        await cb.call(Call("transient"), ctx())
    assert cb.state is CircuitState.OPEN

    clock.advance(5.0)
    with pytest.raises(TransientError):
        await cb.call(Call("transient"), ctx())
    assert cb.state is CircuitState.OPEN  # probe failed -> open again


async def test_half_open_permanent_probe_releases_slot_and_stays_half_open() -> None:
    clock = ManualClock()
    cb = breaker(clock, window=1, failure_threshold=1, reset_timeout=5.0)
    with pytest.raises(TransientError):
        await cb.call(Call("transient"), ctx())
    clock.advance(5.0)

    # The probe hits a permanent error: it says nothing about the service being
    # down, so the slot is freed and the breaker stays half-open (not reopened).
    with pytest.raises(PermanentError):
        await cb.call(Call("permanent"), ctx())
    assert cb.state is CircuitState.HALF_OPEN

    # The next call is admitted as a fresh probe and closes the breaker.
    outcome = await cb.call(Call("ok"), ctx())
    assert outcome.value == "ok"
    assert cb.state is CircuitState.CLOSED


async def test_open_before_reset_still_rejects() -> None:
    clock = ManualClock()
    cb = breaker(clock, window=1, failure_threshold=1, reset_timeout=10.0)
    with pytest.raises(TransientError):
        await cb.call(Call("transient"), ctx())

    clock.advance(9.0)  # not yet elapsed
    with pytest.raises(CircuitOpen):
        await cb.call(Call("ok"), ctx())


async def test_half_open_allows_exactly_one_concurrent_probe() -> None:
    clock = ManualClock()
    cb = breaker(clock, window=1, failure_threshold=1, reset_timeout=5.0)
    with pytest.raises(TransientError):
        await cb.call(Call("transient"), ctx())
    clock.advance(5.0)

    released = anyio.Event()
    started = anyio.Event()
    results: list[str] = []

    async def slow_probe(c: InvocationContext) -> Outcome[Any]:
        started.set()
        await released.wait()
        return Outcome(value="probe-ok")

    async def run_probe() -> None:
        outcome = await cb.call(slow_probe, ctx())
        results.append(str(outcome.value))

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_probe)
        await started.wait()  # probe is now in flight and parked
        # A second call while the probe is in flight must be rejected at once.
        with pytest.raises(CircuitOpen):
            await cb.call(Call("ok"), ctx())
        released.set()

    assert results == ["probe-ok"]
    assert cb.state is CircuitState.CLOSED


async def test_circuit_open_is_transient() -> None:
    assert issubclass(CircuitOpen, TransientError)


async def test_settings_validation() -> None:
    with pytest.raises(ValidationError):
        CircuitBreakerSettings(window=0, failure_threshold=1, reset_timeout=1.0)
    with pytest.raises(ValidationError):
        CircuitBreakerSettings(window=3, failure_threshold=1, reset_timeout=0.0)
    with pytest.raises(ValidationError, match="failure_threshold"):
        CircuitBreakerSettings(window=2, failure_threshold=5, reset_timeout=1.0)


async def test_factory_scope_and_creation() -> None:
    clock = ManualClock()
    factory = CircuitBreakerFactory(CircuitBreakerSettings(window=1, failure_threshold=1, reset_timeout=1.0), clock)
    assert factory.state_scope == ENDPOINT_SCOPE
    assert factory.state_scope.axes == ("endpoint",)

    link = factory.create(())
    base: Next = Call("ok").__call__
    outcome = await link.call(base, ctx())
    assert outcome.value == "ok"
