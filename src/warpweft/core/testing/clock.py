"""Clocks for tests."""

from datetime import UTC, datetime, timedelta

import anyio
import anyio.lowlevel

_EPOCH = datetime(2020, 1, 1, tzinfo=UTC)


class InstantClock:
    """A clock whose ``sleep`` returns immediately, advancing virtual time.

    Retry backoff and any other clock-driven waiting complete with no real
    delay, so a scenario runs in microseconds no matter what delays are
    configured. The durations slept are recorded on `slept` for
    assertions. Use `warpweft.core.clock.ManualClock` instead when a test
    needs to control the passage of time step by step.
    """

    def __init__(self, start: float = 0.0) -> None:
        self._time = start
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self._time

    def now(self) -> datetime:
        return _EPOCH + timedelta(seconds=self._time)

    async def sleep(self, seconds: float) -> None:
        await anyio.lowlevel.checkpoint()  # a real checkpoint, so cancellation still works
        self.slept.append(max(seconds, 0.0))
        self._time += max(seconds, 0.0)
