"""Integration: timeout inside retry around a scripted flaky call.

The pair is composed the way DEFAULT_ORDER prescribes (retry outside,
timeout inside) via build_chain, and exercised under different failure
scripts and setting combinations.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import anyio
import pytest

from halyard.core.axes import AxisRegistry
from halyard.core.context import InvocationContext
from halyard.core.errors import AttemptTimeout, DeadlineExceeded, PermanentError, TransientError
from halyard.core.outcome import Outcome
from halyard.core.pipeline.builtin.retry import RetryFactory, RetrySettings
from halyard.core.pipeline.builtin.timeout import TimeoutFactory, TimeoutSettings
from halyard.core.pipeline.chain import build_chain
from halyard.core.pipeline.interceptor import Next
from halyard.core.pipeline.state import InMemoryStateStore

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


class InstantClock:
    """Sleeps return instantly while virtual time advances; good enough for both links."""

    def __init__(self) -> None:
        self._time = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self._time

    def now(self) -> datetime:
        return datetime(2020, 1, 1, tzinfo=UTC) + timedelta(seconds=self._time)

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self._time += max(seconds, 0.0)


class ScriptedCall:
    """Base call following a script: one entry per call.

    Script entries: "ok", "fail" (transient), "fatal" (permanent),
    "hang" (never returns; only a timeout can stop it).
    """

    def __init__(self, script: list[str]) -> None:
        self.script = script
        self.calls = 0
        self.log: list[str] = []

    async def __call__(self, ctx: InvocationContext) -> Outcome[Any]:
        action = self.script[self.calls] if self.calls < len(self.script) else "ok"
        self.calls += 1
        self.log.append(f"attempt {ctx.attempt}: {action}")
        match action:
            case "ok":
                return Outcome(value=f"done on attempt {ctx.attempt}")
            case "fail":
                raise TransientError(f"scripted failure #{self.calls}")
            case "fatal":
                raise PermanentError("scripted fatal")
            case "hang":
                await anyio.Event().wait()
        raise AssertionError("unreachable")


def make_chain(
    base: Next,
    clock: InstantClock,
    *,
    attempts: int = 4,
    base_delay: float = 0.5,
    max_delay: float = 4.0,
    timeout_seconds: float = 0.02,
) -> Next:
    """Retry outside, timeout inside - as DEFAULT_ORDER prescribes."""
    retry = RetryFactory(
        RetrySettings(attempts=attempts, base_delay=base_delay, max_delay=max_delay, jitter=False),
        clock,
    )
    timeout = TimeoutFactory(TimeoutSettings(seconds=timeout_seconds), clock)
    return build_chain([retry, timeout], InMemoryStateStore(), AxisRegistry(), base)


def ctx(**overrides: Any) -> InvocationContext:
    defaults: dict[str, Any] = {"operation": "op", "correlation_id": "cid"}
    defaults.update(overrides)
    return InvocationContext(**defaults)


@pytest.mark.parametrize(
    ("script", "attempts", "expected_attempts"),
    [
        (["fail", "fail", "ok"], 4, 3),  # classic: two transient failures, then success
        (["ok"], 4, 1),  # immediate success does not touch retry machinery
        (["fail", "ok"], 2, 2),  # success on the last allowed attempt
    ],
)
async def test_failures_then_success(script: list[str], attempts: int, expected_attempts: int) -> None:
    clock = InstantClock()
    call = ScriptedCall(script)
    chain = make_chain(call, clock, attempts=attempts)

    outcome = await chain(ctx())

    assert outcome.value == f"done on attempt {expected_attempts}"
    assert outcome.attempts == expected_attempts
    assert call.calls == expected_attempts


async def test_hang_is_cut_by_timeout_and_retried() -> None:
    """A hanging attempt becomes AttemptTimeout (transient) and the next one succeeds."""
    clock = InstantClock()
    call = ScriptedCall(["hang", "ok"])
    chain = make_chain(call, clock)

    outcome = await chain(ctx())

    assert outcome.attempts == 2
    assert call.log == ["attempt 1: hang", "attempt 2: ok"]


async def test_all_attempts_hang_ends_with_attempt_timeout() -> None:
    clock = InstantClock()
    call = ScriptedCall(["hang", "hang"])
    chain = make_chain(call, clock, attempts=2)

    with pytest.raises(AttemptTimeout):
        await chain(ctx())
    assert call.calls == 2


async def test_permanent_failure_stops_the_whole_chain_at_once() -> None:
    clock = InstantClock()
    call = ScriptedCall(["fatal", "ok"])
    chain = make_chain(call, clock)

    with pytest.raises(PermanentError):
        await chain(ctx())
    assert call.calls == 1
    assert clock.sleeps == []


async def test_expired_deadline_short_circuits_everything() -> None:
    clock = InstantClock()
    clock._time = 100.0
    call = ScriptedCall(["ok"])
    chain = make_chain(call, clock)

    with pytest.raises(DeadlineExceeded):
        await chain(ctx(deadline=50.0))
    assert call.calls == 0


async def test_deadline_cuts_retry_budget_midway() -> None:
    """Backoff 2+4 virtual seconds against a 3-second budget: stop after the first pause."""
    clock = InstantClock()
    call = ScriptedCall(["fail", "fail", "fail", "ok"])
    chain = make_chain(call, clock, base_delay=2.0)

    with pytest.raises(DeadlineExceeded):
        await chain(ctx(deadline=3.0))

    assert call.calls == 2  # attempt 1, sleep 2s, attempt 2 - then 4s does not fit into 1s left
    assert clock.sleeps == [2.0]
    assert clock.monotonic() <= 3.0


async def test_outcome_statistics_are_confirmed_by_the_script_log() -> None:
    clock = InstantClock()
    call = ScriptedCall(["fail", "fail", "ok"])
    chain = make_chain(call, clock, base_delay=1.0, max_delay=8.0)

    outcome = await chain(ctx())

    assert outcome.attempts == 3
    assert outcome.elapsed == pytest.approx(sum(clock.sleeps))
    assert call.log == ["attempt 1: fail", "attempt 2: fail", "attempt 3: ok"]
    assert clock.sleeps == [1.0, 2.0]  # exponential, no jitter
