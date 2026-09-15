"""AComponent: the base every component subclasses.

A plain class, deliberately **not** a ``BaseModel``: it holds live state -
clients, pools, link references. Settings are a field on the instance, not a
base class, and their type is the first generic parameter, so ``self.settings``
is precisely typed rather than ``BaseModel | None``. The lifecycle hooks
default to no-ops so a trivial component writes none of them.

A component declares its remaining metadata as class attributes and marks its
entry points with :func:`invocable`. The derived contract (identity, config
model, per-method schemas and effective policies) is produced by ``describe``
and cached on the class; the settings model is recovered from the generic
argument, so it is declared exactly once.
"""

from typing import Any, ClassVar, Generic, TypeVar, get_args, get_origin

from pydantic import BaseModel

from halyard.core.unit import Identity

from .health import HealthStatus
from .policy import Criticality, Policy

TSettings = TypeVar("TSettings", bound=BaseModel)
TIn = TypeVar("TIn")
TOut = TypeVar("TOut")


class EmptySettings(BaseModel):
    """Settings model for components that need no configuration of their own."""


class AComponent(Generic[TSettings, TIn, TOut]):
    """Base class for components.

    Parameterised as ``AComponent[Settings, In, Out]``. Subclasses set at least
    :attr:`name`. Optional class attributes: :attr:`version`, :attr:`policy`
    (component-wide default), :attr:`dependencies` and :attr:`criticality`. The
    settings model comes from the ``Settings`` type argument - use
    :class:`EmptySettings` for a component that needs none.
    """

    #: Required: the component's stable name.
    name: ClassVar[str]
    #: Optional version; part of the identity uid.
    version: ClassVar[str] = "0"
    #: Component-wide default policy; a method may override it.
    policy: ClassVar[Policy | None] = None
    #: Names of components this one depends on.
    dependencies: ClassVar[tuple[str, ...]] = ()
    #: Whether the system may run without this component.
    criticality: ClassVar[Criticality] = Criticality.REQUIRED

    def __init__(self, settings: TSettings) -> None:
        self.settings: TSettings = settings

    @property
    def identity(self) -> Identity:
        return Identity.of(self.name, self.version)

    @property
    def settings_model(self) -> type[BaseModel] | None:
        """The component's own settings model (for Unit conformance)."""
        return settings_model_of(type(self))

    async def start(self) -> None:
        """Acquire resources. Default: nothing."""

    async def stop(self) -> None:
        """Release resources. Default: nothing."""

    async def health(self) -> HealthStatus:
        """Report health. Default: healthy."""
        return HealthStatus.ok()


def settings_model_of(cls: type["AComponent[Any, Any, Any]"]) -> type[BaseModel] | None:
    """Recover a component's settings model from its ``AComponent[...]`` argument.

    Inspects the class's generic bases and returns the first type argument when
    it is a ``BaseModel`` subclass. Returns ``None`` for a component that never
    parameterised its settings.
    """
    for base in getattr(cls, "__orig_bases__", ()):
        origin = get_origin(base)
        if isinstance(origin, type) and issubclass(origin, AComponent):
            args = get_args(base)
            if args and isinstance(args[0], type) and issubclass(args[0], BaseModel):
                return args[0]
    return None
