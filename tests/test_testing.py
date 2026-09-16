"""The public testing helpers: instant clock, scenarios, drive/drive_policy."""

import pytest

from halyard.core.component import AComponent, EmptySettings, invocable
from halyard.core.errors import AttemptTimeout, PermanentError, RetryExhausted, TransientError
from halyard.core.testing import (
    DictSettingsResolver,
    FakeSettingsResolver,
    InMemoryStateStore,
    InstantClock,
    ManualClock,
    always_permanent,
    always_times_out,
    always_transient,
    drive,
    drive_policy,
    fails_then_succeeds,
    hangs,
)

pytestmark = [pytest.mark.unit, pytest.mark.anyio]

RETRY = {"retry": {"attempts": 5, "base_delay": 1.0, "max_delay": 8.0, "jitter": False}}


async def test_instant_clock_does_not_really_sleep() -> None:
    clock = InstantClock()
    await clock.sleep(3600)
    assert clock.monotonic() == 3600
    assert clock.slept == [3600]
    assert clock.now() > InstantClock().now()  # wall-clock stamp advanced too


async def test_drive_policy_propagates_a_bare_transient() -> None:
    with pytest.raises(TransientError):
        await drive_policy({}, always_transient())  # no links: the error escapes


async def test_hangs_is_cut_by_the_timeout_link() -> None:
    with pytest.raises(AttemptTimeout):
        await drive_policy({"timeout": {"seconds": 0.02}}, hangs())


async def test_drive_policy_recovers_from_transient_failures() -> None:
    clock = InstantClock()
    outcome = await drive_policy(RETRY, fails_then_succeeds(2, value="done"), clock=clock)
    assert outcome.value == "done"
    assert outcome.attempts == 3
    assert clock.slept == [1.0, 2.0]  # two backoffs, none real


async def test_drive_policy_does_not_retry_permanent() -> None:
    with pytest.raises(PermanentError):
        await drive_policy(RETRY, always_permanent())


async def test_drive_policy_exhausts_on_persistent_timeout() -> None:
    with pytest.raises(RetryExhausted) as excinfo:
        await drive_policy({"retry": {"attempts": 3, "base_delay": 0.5, "max_delay": 1.0}}, always_times_out())
    assert excinfo.value.attempts == 3


class Flaky(AComponent[EmptySettings, None, str]):
    name = "flaky-under-test"

    def __init__(self, settings: EmptySettings) -> None:
        super().__init__(settings)
        self.calls = 0

    @invocable
    async def fetch(self) -> str:
        self.calls += 1
        if self.calls < 3:
            raise TransientError(f"warming up {self.calls}")
        return "payload"


async def test_drive_runs_a_real_component_through_its_chain() -> None:
    component = Flaky(EmptySettings())
    outcome = await drive(component, "fetch", config={"policy": RETRY})
    assert outcome.value == "payload"
    assert outcome.attempts == 3
    assert component.calls == 3  # retry re-invoked the real method


async def test_drive_without_a_policy_is_a_bare_call() -> None:
    component = Flaky(EmptySettings())
    with pytest.raises(TransientError):  # no retry configured, first failure escapes
        await drive(component, "fetch")
    assert component.calls == 1


async def test_reexports_are_wired() -> None:
    assert FakeSettingsResolver is DictSettingsResolver
    assert InMemoryStateStore(max_entries=1) is not None
    assert ManualClock().monotonic() == 0.0
