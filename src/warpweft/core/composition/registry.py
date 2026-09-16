"""Type registry: which component types exist.

A registry is an ordinary object, not global state, so a process can hold
several independent ones (tests especially). Registration is explicit - a
decorator or a call, never an import side effect through a metaclass. Building
a descriptor at registration time makes a malformed component fail loudly here
rather than at first use.

Third-party components are discovered through entry points (group
``warpweft.components`` by default).
"""

from collections.abc import Iterable, Mapping
from importlib.metadata import EntryPoint, entry_points
from typing import Any, TypeVar

from warpweft.core.component import AComponent, Descriptor, describe
from warpweft.core.errors import ConfigurationError

#: Default entry-point group third-party components advertise themselves under.
ENTRY_POINT_GROUP = "warpweft.components"

C = TypeVar("C", bound=type[AComponent[Any, Any, Any]])


class Registry:
    """A collection of component types, keyed by their name."""

    def __init__(self) -> None:
        self._types: dict[str, type[AComponent[Any, Any, Any]]] = {}

    def register(self, cls: C) -> C:
        """Register a component type. Usable as a decorator.

        Builds and caches the descriptor (validating the component) and rejects
        a name already taken by a different class.
        """
        descriptor = describe(cls)  # validates name, invocables, scope invariants
        name = descriptor.identity.name
        existing = self._types.get(name)
        if existing is not None and existing is not cls:
            raise ConfigurationError(f"component name '{name}' is already registered to {existing.__qualname__}")
        self._types[name] = cls
        return cls

    def get(self, name: str) -> type[AComponent[Any, Any, Any]]:
        """Return the registered type, or raise if the name is unknown."""
        try:
            return self._types[name]
        except KeyError:
            raise ConfigurationError(f"component '{name}' is not registered") from None

    def descriptor(self, name: str) -> Descriptor:
        """Return the (cached) descriptor of a registered type."""
        return describe(self.get(name))

    def names(self) -> frozenset[str]:
        """Names of all registered types."""
        return frozenset(self._types)

    def __contains__(self, name: object) -> bool:
        return name in self._types

    def load_entry_points(
        self, group: str = ENTRY_POINT_GROUP, source: Iterable[EntryPoint] | None = None
    ) -> Mapping[str, type[AComponent[Any, Any, Any]]]:
        """Discover and register components advertised under ``group``.

        Returns the newly registered types by name. ``source`` overrides the
        entry-point lookup (used by tests); by default the installed
        distributions are scanned.
        """
        discovered = source if source is not None else entry_points(group=group)
        loaded: dict[str, type[AComponent[Any, Any, Any]]] = {}
        for entry_point in discovered:
            cls = entry_point.load()
            self.register(cls)
            loaded[cls.name] = cls
        return loaded
