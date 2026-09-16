"""Runnable demo of the testing helpers.

Shows both testing modes from ``warpweft.core.testing``:
  * ``drive`` - a real component through its real chain, with an injected fake
    that fails twice then succeeds; retry recovers with zero real delay;
  * ``drive_policy`` - a scripted scenario against a policy, no component needed.

Run:
    uv run python examples/testing_a_component.py
"""

from typing import Any, Protocol

import anyio
from pydantic import BaseModel

from warpweft import AComponent, TransientError, invocable
from warpweft.testing import InstantClock, drive, drive_policy, fails_then_succeeds


class Client(Protocol):
    async def fetch(self, user_id: str) -> dict[str, Any]: ...


class ProfilesSettings(BaseModel):
    base_url: str


class Profiles(AComponent[ProfilesSettings, str, dict[str, Any]]):
    name = "profiles"
    _client: Client

    def endpoint(self) -> str | None:
        return self.settings.base_url

    @invocable
    async def get(self, user_id: str) -> dict[str, Any]:
        return await self._client.fetch(user_id)  # the injected client


class FlakyClient:
    """A fake that fails ``fail`` times before returning the payload."""

    def __init__(self, fail: int, payload: dict[str, Any]) -> None:
        self.fail, self.payload, self.calls = fail, payload, 0

    async def fetch(self, user_id: str) -> dict[str, Any]:
        self.calls += 1
        if self.calls <= self.fail:
            raise TransientError("upstream warming up")
        return self.payload


async def main() -> None:
    # 1. Drive a real component through its chain with a fake downstream.
    profiles = Profiles(ProfilesSettings(base_url="https://api.example.com"))
    profiles._client = FlakyClient(fail=2, payload={"id": "42"})
    clock = InstantClock()
    outcome = await drive(
        profiles,
        "get",
        config={"policy": {"retry": {"attempts": 3, "base_delay": 1.0, "max_delay": 5.0, "jitter": False}}},
        clock=clock,
        user_id="42",
    )
    print("drive(profiles.get):")
    print(f"  value    = {outcome.value}")
    print(f"  attempts = {outcome.attempts}  (recovered on the 3rd)")
    print(f"  slept    = {clock.slept}  (virtual seconds, zero real time)")

    # 2. Check a policy against a scripted scenario, no component required.
    scenario = await drive_policy(
        {"retry": {"attempts": 5, "base_delay": 1.0, "max_delay": 8.0, "jitter": False}},
        fails_then_succeeds(2, value="ok"),
    )
    print("\ndrive_policy(fails_then_succeeds(2)):")
    print(f"  value    = {scenario.value}")
    print(f"  attempts = {scenario.attempts}")


if __name__ == "__main__":
    anyio.run(main)
