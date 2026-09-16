"""Testing helpers for component authors (public API).

Everything needed to test a component without a running system: an instant
clock so backoff never really waits, fakes for the state store and settings
resolver, scripted base calls, and ``drive`` / ``drive_policy`` to run a
component (or a scenario) through its real policy chain.
"""

from warpweft.core.clock import ManualClock
from warpweft.core.composition.config import DictSettingsResolver
from warpweft.core.pipeline.state import InMemoryStateStore

from .clock import InstantClock
from .harness import drive, drive_policy
from .scenarios import (
    always_permanent,
    always_times_out,
    always_transient,
    fails_then_succeeds,
    hangs,
)

#: Alias making the intent explicit in tests.
FakeSettingsResolver = DictSettingsResolver

__all__ = [
    "DictSettingsResolver",
    "FakeSettingsResolver",
    "InMemoryStateStore",
    "InstantClock",
    "ManualClock",
    "always_permanent",
    "always_times_out",
    "always_transient",
    "drive",
    "drive_policy",
    "fails_then_succeeds",
    "hangs",
]
