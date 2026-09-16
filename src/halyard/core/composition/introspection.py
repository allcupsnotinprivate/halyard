"""Introspection results: what a method resolves to, and live runtime state.

These answer the questions that otherwise mean reading the core's source: which
links actually wrap a method and where each setting came from, what an
instance's resolved config is, and the current state of breakers, concurrency
semaphores and live slice keys.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from halyard.core.axes import ScopeKey


@dataclass(frozen=True)
class MethodExplanation:
    """The effective chain of a method and the provenance of its config."""

    component: str
    method: str
    #: Active link names, outermost first.
    chain: tuple[str, ...]
    #: Config field path -> the source that set it.
    provenance: Mapping[str, str]


@dataclass(frozen=True)
class BreakerSnapshot:
    """One circuit breaker instance's live state."""

    unit: str
    slice: ScopeKey
    state: str


@dataclass(frozen=True)
class ConcurrencySnapshot:
    """One concurrency instance's live occupancy."""

    unit: str
    slice: ScopeKey
    outer_limit: int
    outer_available: int
    inner_slices: int


@dataclass(frozen=True)
class RuntimeSnapshot:
    """A point-in-time view of runtime link state and live slices."""

    breakers: tuple[BreakerSnapshot, ...]
    concurrency: tuple[ConcurrencySnapshot, ...]
    #: Scoped component name -> its currently live slice keys.
    live_slices: Mapping[str, tuple[ScopeKey, ...]]
