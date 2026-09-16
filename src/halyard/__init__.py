"""Halyard: a declarative framework for resilient, observable service components.

The everyday API is re-exported here, so applications import from ``halyard``
directly::

    from halyard import App, AComponent, invocable, component

The internal layers remain importable (``halyard.core.*``, ``halyard.runtime.*``)
and a few focused surfaces have their own module: :mod:`halyard.formats` (field
formats), :mod:`halyard.testing` (testing helpers), and :mod:`halyard.mcp`
(Model Context Protocol tools, available with the ``mcp`` extra).
"""

from halyard.core import __version__
from halyard.core.axes import Axis, AxisRegistry, ScopeKey, ScopeSpec
from halyard.core.clock import Clock, ManualClock, SystemClock
from halyard.core.component import (
    AComponent,
    Criticality,
    Descriptor,
    EmptySettings,
    Health,
    HealthStatus,
    Lifetime,
    Policy,
    describe,
    invocable,
)
from halyard.core.composition import Container, Readiness, Registry, SettingsResolver
from halyard.core.context import (
    InvocationContext,
    current_correlation_id,
    use_correlation_id,
)
from halyard.core.errors import (
    AttemptTimeout,
    CircuitOpen,
    ComponentUnavailable,
    ConfigurationError,
    DeadlineExceeded,
    DefaultErrorClassifier,
    ErrorClass,
    ErrorClassifier,
    FrameworkError,
    PermanentError,
    RetryExhausted,
    StartupError,
    TransientError,
)
from halyard.core.formats import Format
from halyard.core.outcome import Outcome
from halyard.runtime import App, AxisHandle, autodiscover, component, default_registry

__all__ = [
    "AComponent",
    "App",
    "AttemptTimeout",
    "Axis",
    "AxisHandle",
    "AxisRegistry",
    "CircuitOpen",
    "Clock",
    "ComponentUnavailable",
    "ConfigurationError",
    "Container",
    "Criticality",
    "DeadlineExceeded",
    "DefaultErrorClassifier",
    "Descriptor",
    "EmptySettings",
    "ErrorClass",
    "ErrorClassifier",
    "Format",
    "FrameworkError",
    "Health",
    "HealthStatus",
    "InvocationContext",
    "Lifetime",
    "ManualClock",
    "Outcome",
    "PermanentError",
    "Policy",
    "Readiness",
    "Registry",
    "RetryExhausted",
    "ScopeKey",
    "ScopeSpec",
    "SettingsResolver",
    "StartupError",
    "SystemClock",
    "TransientError",
    "__version__",
    "autodiscover",
    "component",
    "current_correlation_id",
    "default_registry",
    "describe",
    "invocable",
    "use_correlation_id",
]
