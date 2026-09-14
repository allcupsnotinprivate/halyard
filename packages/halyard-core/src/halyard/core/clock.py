"""Clock protocol with system and manual (test) implementations.

Every time-dependent piece of the framework takes a ``Clock`` through its
constructor. Interceptor code never calls ``time.monotonic()`` or an event
loop ``sleep`` directly - that is what makes backoff and deadline logic
testable without real waiting.
"""

from datetime import UTC, datetime, timedelta
import time
from typing import Protocol

import anyio
import anyio.lowlevel


class Clock(Protocol):
    """Source of time for deadlines, telemetry stamps and sleeping."""

    def monotonic(self) -> float:
        """Monotonic seconds; immune to wall-clock adjustments. Use for deadlines."""
        ...

    def now(self) -> datetime:
        """Wall-clock timestamp (timezone-aware). Use for telemetry marks."""
        ...

    async def sleep(self, seconds: float) -> None:
        """Sleep for ``seconds``; must be a checkpoint even for zero/negative values."""
        ...


class SystemClock:
    """Real time: ``time.monotonic`` + ``anyio.sleep``."""

    def monotonic(self) -> float:
        return time.monotonic()

    def now(self) -> datetime:
        return datetime.now(UTC)

    async def sleep(self, seconds: float) -> None:
        await anyio.sleep(max(seconds, 0))


class ManualClock:
    """Virtual time advanced explicitly by tests.

    ``sleep`` never waits in real time: it parks the caller until ``advance``
    moves virtual time past its wake-up point. Retry/backoff tests run
    instantly and without flakes.
    """

    _EPOCH = datetime(2020, 1, 1, tzinfo=UTC)

    def __init__(self, start: float = 0.0) -> None:
        self._time = start
        self._sleepers: list[tuple[float, anyio.Event]] = []

    def monotonic(self) -> float:
        return self._time

    def now(self) -> datetime:
        return self._EPOCH + timedelta(seconds=self._time)

    @property
    def pending(self) -> int:
        """Number of tasks currently parked in ``sleep`` (for test synchronization)."""
        return len(self._sleepers)

    async def wait_for_sleepers(self, count: int = 1) -> None:
        """Yield to the scheduler until at least ``count`` tasks are sleeping."""
        while len(self._sleepers) < count:
            await anyio.lowlevel.checkpoint()

    async def sleep(self, seconds: float) -> None:
        if seconds <= 0:
            await anyio.lowlevel.checkpoint()
            return
        event = anyio.Event()
        self._sleepers.append((self._time + seconds, event))
        await event.wait()

    def advance(self, seconds: float) -> None:
        """Move virtual time forward and wake every sleeper whose time has come."""
        if seconds < 0:
            raise ValueError("cannot advance backwards")
        self._time += seconds
        due = [(when, event) for when, event in self._sleepers if when <= self._time]
        self._sleepers = [(when, event) for when, event in self._sleepers if when > self._time]
        for _, event in due:
            event.set()
