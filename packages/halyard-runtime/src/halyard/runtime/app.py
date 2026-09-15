"""The App facade: registry + configuration + container lifecycle in one object.

``App`` owns a type registry and builds/starts/stops the core ``Container``.
Configuration merges the programmatic mapping with environment variables
(environment wins, field by field). Registration stays explicit - the
``@component`` decorator - while :func:`halyard.runtime.discovery.autodiscover`
removes the manual import list.

The module-level :func:`component` decorator registers into a process-wide
default registry (the convenient path, like Celery's ``shared_task``). For
full isolation - several independent apps in one process, hermetic tests -
give each ``App`` its own ``Registry`` and use ``@app.component`` instead.
"""

from collections.abc import AsyncIterator, Mapping
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any, TypeVar

from halyard.core.component import AComponent
from halyard.core.composition import Container, Registry
from halyard.core.composition.config import deep_merge
from halyard.core.errors import ConfigurationError
from halyard.core.outcome import Outcome

from .discovery import autodiscover
from .envconfig import collect_env_config

C = TypeVar("C", bound=AComponent[Any, Any, Any])
T = TypeVar("T", bound=type[AComponent[Any, Any, Any]])

_SOURCE_ENV = "environment"
_SOURCE_CONFIG = "app config"

_default_registry = Registry()


def default_registry() -> Registry:
    """The process-wide registry the module-level decorator writes to."""
    return _default_registry


def component(cls: T) -> T:
    """Register a component type in the default registry. Use as a decorator."""
    return _default_registry.register(cls)


class App:
    """An application: registered components, their config, one container."""

    def __init__(
        self,
        *,
        env_prefix: str | None = None,
        config: Mapping[str, Mapping[str, Any]] | None = None,
        registry: Registry | None = None,
        environ: Mapping[str, str] | None = None,
        **build_options: Any,
    ) -> None:
        self._registry = registry if registry is not None else _default_registry
        self._env_prefix = env_prefix
        self._environ = environ
        self._config = {name: dict(section) for name, section in (config or {}).items()}
        self._build_options = build_options
        self._container: Container | None = None

    @property
    def registry(self) -> Registry:
        return self._registry

    def component(self, cls: T) -> T:
        """Register a component type in this app's registry. Use as a decorator."""
        return self._registry.register(cls)

    def autodiscover(self, *packages: str) -> tuple[str, ...]:
        """Import the packages' modules so their ``@component`` decorators fire."""
        return autodiscover(*packages)

    def config_mapping(self) -> dict[str, dict[str, Any]]:
        """The deployment config: every registered component, env over config.

        Each registered component is included (an absent section means "all
        defaults"); environment values override the programmatic config field
        by field.
        """
        env_config: dict[str, dict[str, Any]] = {}
        if self._env_prefix is not None:
            env_config = collect_env_config(self._registry.names(), self._env_prefix, self._environ)

        merged: dict[str, dict[str, Any]] = {}
        for name in sorted(self._registry.names()):
            section, _ = deep_merge(
                [
                    (_SOURCE_CONFIG, self._config.get(name, {})),
                    (_SOURCE_ENV, env_config.get(name, {})),
                ]
            )
            merged[name] = section
        return merged

    # --- lifecycle -------------------------------------------------------

    async def start(self) -> Container:
        """Build the container from the merged config and start it."""
        if self._container is not None:
            return self._container
        container = Container.build(self._registry, self.config_mapping(), **self._build_options)
        await container.start()
        self._container = container
        return container

    async def stop(self) -> None:
        if self._container is None:
            return
        await self._container.stop()
        self._container = None

    @asynccontextmanager
    async def run(self) -> AsyncIterator[Container]:
        """``async with app.run() as container:`` - start now, stop on exit."""
        container = await self.start()
        try:
            yield container
        finally:
            await self.stop()

    @property
    def container(self) -> Container:
        if self._container is None:
            raise ConfigurationError("app is not started")
        return self._container

    # --- passthroughs ------------------------------------------------------

    async def invoke(self, component_name: str, method: str, **arguments: Any) -> Outcome[Any]:
        return await self.container.invoke(component_name, method, **arguments)

    async def get(self, ref: type[C] | str) -> C:
        return await self.container.get(ref)

    def proxy(self, ref: type[C] | str) -> C:
        return self.container.proxy(ref)

    # --- embedding into a host ------------------------------------------------

    def lifespan(self, *_: Any) -> AbstractAsyncContextManager[None]:
        """A framework-agnostic lifespan: start on enter, stop (drained) on exit.

        Accepts and ignores whatever a host passes (ASGI frameworks pass their
        application object), so the bound method plugs in directly::

            FastAPI(lifespan=app.lifespan)      # or Starlette(lifespan=...)
            async with app.lifespan():          # or standalone

        Nothing is published into the host: reach the running system through
        this object (``app.container``, ``app.proxy(...)``, ``app.invoke(...)``).
        Hosts with startup/shutdown callback pairs instead of a lifespan can
        call :meth:`start` and :meth:`stop` directly.
        """
        return self._lifespan()

    @asynccontextmanager
    async def _lifespan(self) -> AsyncIterator[None]:
        await self.start()
        try:
            yield
        finally:
            await self.stop()
