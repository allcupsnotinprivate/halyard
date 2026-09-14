"""Unit protocol and Identity: uniform configuration and lifecycle.

Components and interceptors are not subtypes of each other, yet
both need to be configured, registered and started/stopped uniformly. Unit
is deliberately a Protocol, not an ABC: the layers conform to it
independently, without sharing a base class.
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from pydantic import BaseModel


@dataclass(frozen=True, slots=True)
class Identity:
    """Stable identity of a unit: for state keys, metrics labels and logs."""

    name: str
    version: str
    uid: str

    @classmethod
    def of(cls, name: str, version: str = "0") -> "Identity":
        """Build an identity with the conventional ``name@version`` uid."""
        return cls(name=name, version=version, uid=f"{name}@{version}")


class Unit(Protocol):
    """What every configurable framework unit looks like."""

    @property
    def identity(self) -> Identity: ...

    @property
    def settings_model(self) -> type[BaseModel] | None:
        """Pydantic model describing the unit's settings, if it has any."""
        ...


@runtime_checkable
class Startable(Protocol):
    """Optional lifecycle: units that need explicit startup."""

    async def start(self) -> None: ...


@runtime_checkable
class Stoppable(Protocol):
    """Optional lifecycle: units that must be released (called on eviction)."""

    async def stop(self) -> None: ...
