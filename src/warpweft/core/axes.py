"""State-slicing axes: Axis, ScopeSpec, ScopeKey, AxisRegistry.

Axes replace any built-in notion of a tenant: state is sliced along named
dimensions, and what "tenant" means is up to the resolver of a particular
axis (contextvar, instance settings, environment - the axis does not care).
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, TypeAlias

from .errors import ConfigurationError

#: Canonical result of resolving a ScopeSpec: immutable, hashable,
#: sorted by axis name (see AxisRegistry.resolve).
ScopeKey: TypeAlias = tuple[tuple[str, str], ...]

#: Key of the process-wide scope (empty spec).
GLOBAL_SCOPE: ScopeKey = ()


@dataclass(frozen=True, slots=True)
class Axis:
    """Named dimension along which state is sliced.

    ``resolver`` returns the current value of the dimension or ``None`` when
    it has no value in the calling context. Where the value comes from is
    the resolver's business.
    """

    name: str
    resolver: Callable[[], str | None]
    on_missing: Literal["required", "default"] = "required"
    default: str | None = None
    max_cardinality: int = 1000

    def __post_init__(self) -> None:
        if not self.name:
            raise ConfigurationError("axis name must be non-empty")
        if self.on_missing == "default" and self.default is None:
            raise ConfigurationError(f"axis '{self.name}': on_missing='default' requires a default value")
        if self.max_cardinality < 1:
            raise ConfigurationError(f"axis '{self.name}': max_cardinality must be positive")

    def resolve(self) -> str | None:
        """Return the current value of the axis, or ``None`` if absent."""
        return self.resolver()


@dataclass(frozen=True, slots=True)
class ScopeSpec:
    """Set of axis names describing how a unit's state is sliced.

    An empty spec means "one instance per process". Order does not matter:
    the resulting ScopeKey is always canonicalized by axis name.
    """

    axes: tuple[str, ...] = ()

    def __init__(self, axes: tuple[str, ...] | list[str] = ()) -> None:
        unique = tuple(axes)
        if len(set(unique)) != len(unique):
            raise ConfigurationError(f"duplicate axis names in scope spec: {unique!r}")
        object.__setattr__(self, "axes", unique)

    def __bool__(self) -> bool:
        return bool(self.axes)


#: Empty spec: state is process-wide.
EMPTY_SCOPE = ScopeSpec()


@dataclass
class AxisRegistry:
    """Registration of axes by name and resolution of specs into keys."""

    _axes: dict[str, Axis] = field(default_factory=dict)

    def register(self, axis: Axis) -> None:
        if axis.name in self._axes:
            raise ConfigurationError(f"axis '{axis.name}' is already registered")
        self._axes[axis.name] = axis

    def get(self, name: str) -> Axis:
        try:
            return self._axes[name]
        except KeyError:
            raise ConfigurationError(f"axis '{name}' is not registered") from None

    def resolve(self, spec: ScopeSpec) -> ScopeKey:
        """Resolve every axis of ``spec`` into a canonical ScopeKey.

        Canonicalization: pairs are sorted by axis name, so specs listing
        the same axes in different order produce an identical key.
        """
        pairs: list[tuple[str, str]] = []
        for name in spec.axes:
            axis = self.get(name)
            value = axis.resolve()
            if value is None:
                if axis.on_missing == "default":
                    # __post_init__ guarantees default is not None here.
                    assert axis.default is not None  # noqa: S101 - invariant, not validation
                    value = axis.default
                else:
                    raise ConfigurationError(f"axis '{name}' is required but has no value in the current context")
            pairs.append((name, value))
        return tuple(sorted(pairs))
