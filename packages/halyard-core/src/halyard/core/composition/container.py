"""Instance container: what is configured and running in this process.

Distinct from the registry (which types *exist*): the container is built from
configuration, validates the dependency graph, starts components in dependency
order, wires each invocable method through its policy chain (telemetry outside),
and stops in reverse with a drain. It holds no global state, so a process can
run several independent containers.

Endpoint slicing works here for the first time: each invocation binds the
current endpoint from the instance's settings, and ``[endpoint]``-sliced link
state (breaker, concurrency) is shared through one link store across instances
that talk to the same endpoint.
"""

from collections.abc import Mapping
import contextlib
from dataclasses import dataclass
from typing import Any
import uuid

import anyio
import anyio.lowlevel
from pydantic import BaseModel

from halyard.core.axes import GLOBAL_SCOPE, AxisRegistry, ScopeKey
from halyard.core.clock import Clock, SystemClock
from halyard.core.component import AComponent, Criticality, Descriptor, HealthStatus, Lifetime
from halyard.core.component.settings import POLICY_FIELD
from halyard.core.context import InvocationContext, use_context
from halyard.core.errors import (
    ComponentUnavailable,
    ConfigurationError,
    DefaultErrorClassifier,
    ErrorClassifier,
    StartupError,
)
from halyard.core.outcome import Outcome
from halyard.core.pipeline.builtin.circuit_breaker import CircuitBreakerInterceptor
from halyard.core.pipeline.builtin.concurrency import ConcurrencyInterceptor
from halyard.core.pipeline.chain import build_chain
from halyard.core.pipeline.interceptor import Next
from halyard.core.pipeline.state import InMemoryStateStore
from halyard.core.telemetry.instrument import DEFAULT_CONFIG, TelemetryConfig, instrument

from .config import (
    SOURCE_COMPONENT,
    SOURCE_DEPLOYMENT,
    SOURCE_FRAMEWORK,
    SOURCE_SLICE,
    DictSettingsResolver,
    Provenance,
    SettingsResolver,
    assemble_config,
)
from .endpoint import endpoint_axis, use_endpoint
from .graph import DependencyGraph, GraphNode
from .health import Readiness, aggregate_readiness
from .introspection import (
    BreakerSnapshot,
    ConcurrencySnapshot,
    MethodExplanation,
    RuntimeSnapshot,
)
from .registry import Registry
from .wiring import active_links, make_base, method_factories


def _first_leaf(exc: BaseException) -> BaseException:
    """Unwrap a (Base)ExceptionGroup to its first leaf exception."""
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return exc


@dataclass(frozen=True)
class _Registration:
    name: str
    cls: type[AComponent[Any, Any, Any]]
    descriptor: Descriptor
    deployment: Mapping[str, Any]


class Container:
    """A configured, runnable set of components and their pipelines."""

    def __init__(
        self,
        registrations: Mapping[str, _Registration],
        graph: DependencyGraph,
        *,
        clock: Clock,
        classifier: ErrorClassifier,
        axes: AxisRegistry,
        tracer_provider: Any,
        meter_provider: Any,
        telemetry: TelemetryConfig,
        framework_defaults: Mapping[str, Any],
        resolver: SettingsResolver,
        init_timeout: float,
        drain_timeout: float,
        health_timeout: float,
        scoped_max_entries: int,
    ) -> None:
        self._registrations = dict(registrations)
        self._graph = graph
        self._clock = clock
        self._classifier = classifier
        self._axes = axes
        self._framework_defaults = framework_defaults
        self._resolver = resolver
        self._config_cache: dict[tuple[str, ScopeKey], BaseModel] = {}
        self._provenance_cache: dict[tuple[str, ScopeKey], Provenance] = {}
        self._tracer_provider = tracer_provider
        self._meter_provider = meter_provider
        self._telemetry = telemetry
        self._init_timeout = init_timeout
        self._drain_timeout = drain_timeout
        self._health_timeout = health_timeout
        self._link_store = InMemoryStateStore(max_entries=scoped_max_entries)
        self._scoped_stores: dict[str, InMemoryStateStore] = {}
        self._scoped_max_entries = scoped_max_entries
        self._process: dict[str, AComponent[Any, Any, Any]] = {}
        self._process_chains: dict[tuple[str, str], Next] = {}
        self._degraded: set[str] = set()
        self._active_calls = 0
        self._started = False

    # --- construction --------------------------------------------------------

    @classmethod
    def build(
        cls,
        registry: Registry,
        configs: Mapping[str, Mapping[str, Any]],
        *,
        clock: Clock | None = None,
        classifier: ErrorClassifier | None = None,
        axes: AxisRegistry | None = None,
        tracer_provider: Any = None,
        meter_provider: Any = None,
        telemetry: TelemetryConfig = DEFAULT_CONFIG,
        framework_defaults: Mapping[str, Any] | None = None,
        resolver: SettingsResolver | None = None,
        init_timeout: float = 30.0,
        drain_timeout: float = 30.0,
        health_timeout: float = 5.0,
        scoped_max_entries: int = 1000,
    ) -> "Container":
        """Validate configs and the dependency graph; return an unstarted container.

        Deployment config is validated eagerly (framework + component defaults +
        deployment); per-slice overrides are applied and re-validated per
        instance. Required fields must come from the deployment config - a slice
        override tunes existing fields, it does not supply missing ones.
        """
        axes = axes or AxisRegistry()
        framework_defaults = framework_defaults or {}
        with contextlib.suppress(ConfigurationError):
            axes.register(endpoint_axis())  # tolerate a caller-registered endpoint axis

        registrations: dict[str, _Registration] = {}
        for name, raw in configs.items():
            component_cls = registry.get(name)
            descriptor = registry.descriptor(name)
            # Fail fast on deployment errors (without the per-slice layer).
            assemble_config(
                name,
                descriptor.config_model,
                [
                    (SOURCE_FRAMEWORK, framework_defaults),
                    (SOURCE_COMPONENT, component_cls.defaults),
                    (SOURCE_DEPLOYMENT, dict(raw)),
                ],
            )
            registrations[name] = _Registration(name, component_cls, descriptor, dict(raw))

        graph = DependencyGraph(
            {
                name: GraphNode(name, reg.descriptor.dependencies, reg.descriptor.lifetime)
                for name, reg in registrations.items()
            }
        )
        return cls(
            registrations,
            graph,
            clock=clock or SystemClock(),
            classifier=classifier or DefaultErrorClassifier(),
            axes=axes,
            tracer_provider=tracer_provider,
            meter_provider=meter_provider,
            telemetry=telemetry,
            framework_defaults=framework_defaults,
            resolver=resolver or DictSettingsResolver(),
            init_timeout=init_timeout,
            drain_timeout=drain_timeout,
            health_timeout=health_timeout,
            scoped_max_entries=scoped_max_entries,
        )

    # --- lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        """Start process components in dependency order; scoped ones stay lazy."""
        if self._started:
            return
        for name, reg in self._registrations.items():
            if reg.descriptor.lifetime is Lifetime.SCOPED:
                self._scoped_stores[name] = InMemoryStateStore(max_entries=self._scoped_max_entries)
        try:
            for layer in self._graph.startup_layers():
                names = [n for n in layer if self._registrations[n].descriptor.lifetime is Lifetime.PROCESS]
                async with anyio.create_task_group() as tg:
                    for name in names:
                        tg.start_soon(self._start_process, name)
        except BaseException as exc:
            await self._stop_process_instances()
            # A task group reports child failures as a (Base)ExceptionGroup;
            # surface the underlying error so callers see StartupError directly.
            raise _first_leaf(exc) from None

        for name, reg in self._registrations.items():
            if reg.descriptor.lifetime is Lifetime.PROCESS and name in self._process:
                config = self._assemble(name, GLOBAL_SCOPE)
                for method in reg.descriptor.invocables:
                    self._process_chains[(name, method)] = self._build_chain(self._process[name], name, method, config)
        self._started = True

    async def _start_process(self, name: str) -> None:
        reg = self._registrations[name]
        instance, _ = self._instantiate(name, GLOBAL_SCOPE)
        instance.bind_dependencies({d: self._process[d] for d in reg.descriptor.dependencies if d in self._process})
        try:
            with anyio.fail_after(self._init_timeout):
                await instance.start()
        except Exception as exc:
            if reg.descriptor.criticality is Criticality.REQUIRED:
                raise StartupError(f"required component '{name}' failed to start: {exc}") from exc
            self._degraded.add(name)
            return
        self._process[name] = instance

    async def stop(self) -> None:
        """Drain active calls, then stop everything in reverse dependency order."""
        if not self._started:
            return
        with anyio.move_on_after(self._drain_timeout):
            while self._active_calls > 0:
                await anyio.lowlevel.checkpoint()  # yield so in-flight calls finish
        await self._stop_process_instances()
        for store in self._scoped_stores.values():
            await store.close()
        self._scoped_stores.clear()
        await self._link_store.close()
        self._started = False

    async def _stop_process_instances(self) -> None:
        for name in self._graph.shutdown_order():
            instance = self._process.pop(name, None)
            if instance is None:
                continue
            with anyio.move_on_after(self._drain_timeout):
                await instance.stop()
        self._process_chains.clear()

    # --- invocation ----------------------------------------------------------

    async def invoke(
        self, component: str, method: str, *, correlation_id: str | None = None, **arguments: Any
    ) -> Outcome[Any]:
        """Invoke a component's method through its policy chain and telemetry."""
        if not self._started:
            raise ConfigurationError("container is not started")
        reg = self._registration(component)
        if method not in reg.descriptor.invocables:
            raise ConfigurationError(f"component '{component}' has no invocable '{method}'")

        if reg.descriptor.lifetime is Lifetime.PROCESS:
            instance = self._process.get(component)
            if instance is None:
                raise ComponentUnavailable(f"component '{component}' is degraded")
            chain = self._process_chains[(component, method)]
            scope_key: ScopeKey = (("component", component),)
        else:
            instance, scope_key = await self._scoped_instance(component)
            chain = self._build_chain(instance, component, method, self._assemble(component, scope_key))

        ctx = InvocationContext(
            operation=f"{component}.{method}",
            correlation_id=correlation_id or uuid.uuid4().hex,
            arguments=dict(arguments),
            scope_key=scope_key,
            clock=self._clock,
        )
        endpoint = instance.endpoint() or instance.identity.uid
        self._active_calls += 1
        try:
            with use_endpoint(endpoint), use_context(ctx):
                return await chain(ctx)
        finally:
            self._active_calls -= 1

    async def _scoped_instance(self, component: str) -> tuple[AComponent[Any, Any, Any], ScopeKey]:
        reg = self._registrations[component]
        scope_key = self._axes.resolve(reg.descriptor.scope)
        deps = await self._resolve_dependencies(reg.descriptor.dependencies)
        store = self._scoped_stores[component]

        def factory() -> AComponent[Any, Any, Any]:
            instance, _ = self._instantiate(component, scope_key)
            instance.bind_dependencies(deps)
            return instance

        instance = await store.get_or_create(scope_key, factory)
        return instance, scope_key

    async def _resolve_dependencies(self, names: tuple[str, ...]) -> dict[str, AComponent[Any, Any, Any]]:
        resolved: dict[str, AComponent[Any, Any, Any]] = {}
        for name in names:
            reg = self._registrations[name]
            if reg.descriptor.lifetime is Lifetime.PROCESS:
                if name in self._process:
                    resolved[name] = self._process[name]
            else:
                instance, _ = await self._scoped_instance(name)
                resolved[name] = instance
        return resolved

    # --- wiring --------------------------------------------------------------

    def _registration(self, component: str) -> _Registration:
        try:
            return self._registrations[component]
        except KeyError:
            raise ConfigurationError(f"component '{component}' is not configured") from None

    def _assemble(self, name: str, scope_key: ScopeKey) -> BaseModel:
        """Merge the four config layers for an instance and cache the result."""
        cached = self._config_cache.get((name, scope_key))
        if cached is not None:
            return cached
        reg = self._registrations[name]
        config, provenance = assemble_config(
            name,
            reg.descriptor.config_model,
            [
                (SOURCE_FRAMEWORK, self._framework_defaults),
                (SOURCE_COMPONENT, reg.cls.defaults),
                (SOURCE_DEPLOYMENT, reg.deployment),
                (SOURCE_SLICE, dict(self._resolver.resolve(name, scope_key))),
            ],
        )
        self._config_cache[(name, scope_key)] = config
        self._provenance_cache[(name, scope_key)] = provenance
        return config

    def _instantiate(self, name: str, scope_key: ScopeKey) -> tuple[AComponent[Any, Any, Any], BaseModel]:
        reg = self._registrations[name]
        config = self._assemble(name, scope_key)
        own = reg.descriptor.settings_model
        if own is None:
            return reg.cls(config), config
        settings = own.model_validate(config.model_dump(exclude={POLICY_FIELD}))
        return reg.cls(settings), config

    def _build_chain(self, instance: AComponent[Any, Any, Any], name: str, method: str, config: BaseModel) -> Next:
        spec = self._registrations[name].descriptor.invocables[method]
        factories = method_factories(config, spec.policy, self._clock, self._classifier)
        base = make_base(instance, spec.method_name)
        chain = build_chain(factories, self._link_store, self._axes, base)
        return instrument(
            chain,
            clock=self._clock,
            tracer_provider=self._tracer_provider,
            meter_provider=self._meter_provider,
            config=self._telemetry,
        )

    # --- health --------------------------------------------------------------

    async def liveness(self) -> HealthStatus:
        """Is the process up? Dependencies are not consulted."""
        return HealthStatus.ok() if self._started else HealthStatus.unhealthy("not started")

    async def readiness(self) -> Readiness:
        """Can the system serve? Required components must be healthy."""
        own = {name: await self._component_status(name) for name in self._registrations}
        dependencies = {name: reg.descriptor.dependencies for name, reg in self._registrations.items()}
        criticality = {name: reg.descriptor.criticality for name, reg in self._registrations.items()}
        return aggregate_readiness(dependencies, criticality, own)

    async def _component_status(self, name: str) -> HealthStatus:
        reg = self._registrations[name]
        if reg.descriptor.lifetime is Lifetime.SCOPED:
            return HealthStatus.ok()  # created on demand; nothing running to poll
        if name in self._degraded:
            return HealthStatus.degraded("failed to start")
        instance = self._process.get(name)
        if instance is None:
            return HealthStatus.unhealthy("not running")
        try:
            with anyio.fail_after(self._health_timeout):
                return await instance.health()  # via timeout only, not the full chain
        except Exception:
            return HealthStatus.unhealthy("health check failed")

    # --- introspection -------------------------------------------------------

    def explain(self, component: str, method: str, *, scope_key: ScopeKey = GLOBAL_SCOPE) -> MethodExplanation:
        """Show a method's effective link chain and where each setting came from."""
        reg = self._registration(component)
        if method not in reg.descriptor.invocables:
            raise ConfigurationError(f"component '{component}' has no invocable '{method}'")
        config = self._assemble(component, scope_key)
        spec = reg.descriptor.invocables[method]
        chain = tuple(link for link, _ in active_links(config, spec.policy))
        provenance = dict(self._provenance_cache.get((component, scope_key), {}))
        return MethodExplanation(component=component, method=method, chain=chain, provenance=provenance)

    def resolved_settings(self, component: str, *, scope_key: ScopeKey = GLOBAL_SCOPE) -> Mapping[str, Any]:
        """The fully resolved config of an instance as a plain mapping."""
        self._registration(component)
        return self._assemble(component, scope_key).model_dump()

    def snapshot(self) -> RuntimeSnapshot:
        """A point-in-time view of breaker states, concurrency and live slices."""
        breakers: list[BreakerSnapshot] = []
        concurrency: list[ConcurrencySnapshot] = []
        for key, instance in self._link_store.items():
            unit = key[0][1] if key and key[0][0] == "__unit__" else "?"
            slice_key = key[1:]
            if isinstance(instance, CircuitBreakerInterceptor):
                breakers.append(BreakerSnapshot(unit=unit, slice=slice_key, state=instance.state.value))
            elif isinstance(instance, ConcurrencyInterceptor):
                concurrency.append(
                    ConcurrencySnapshot(
                        unit=unit,
                        slice=slice_key,
                        outer_limit=instance.outer_limit,
                        outer_available=instance.outer_available,
                        inner_slices=instance.inner_slice_count,
                    )
                )
        live_slices = {name: tuple(store.keys()) for name, store in self._scoped_stores.items()}
        return RuntimeSnapshot(tuple(breakers), tuple(concurrency), live_slices)

    @property
    def started(self) -> bool:
        return self._started

    def is_degraded(self, name: str) -> bool:
        return name in self._degraded
