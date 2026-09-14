"""Outcome[T]: call result with source, degradation flag and stats.

A call returns an Outcome rather than a bare value so that degradation is
explicit: the caller can always tell a live result from a cached or stubbed
one. Only ``live`` is used until the cache/stub interceptors exist, but the
fields are laid down now to keep signatures stable.
"""

from dataclasses import dataclass
from typing import Generic, Literal, TypeAlias, TypeVar

T = TypeVar("T")

OutcomeSource: TypeAlias = Literal["live", "cache", "stub"]


@dataclass(frozen=True, slots=True)
class Outcome(Generic[T]):
    """Result of an invocation plus how it was obtained."""

    value: T
    source: OutcomeSource = "live"
    degraded: bool = False
    attempts: int = 1
    elapsed: float = 0.0
