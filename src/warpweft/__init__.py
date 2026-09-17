"""Warpweft: a declarative framework for resilient, observable service components.

The everyday API is re-exported here, so applications import from ``warpweft``
directly::

    from warpweft import App, AComponent, invocable, component

The internal layers remain importable (``warpweft.core.*``, ``warpweft.runtime.*``)
and a few focused surfaces have their own module: `warpweft.formats` (field
formats), `warpweft.testing` (testing helpers), `warpweft.actions`
(actions and providers), and `warpweft.mcp` (Model Context Protocol tools,
available with the ``mcp`` extra).
"""

from warpweft.actions import Action, ActionParams, Provider
from warpweft.core import __version__
from warpweft.core.axes import Axis, AxisRegistry, ScopeKey, ScopeSpec
from warpweft.core.clock import Clock, ManualClock, SystemClock
from warpweft.core.component import (
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
from warpweft.core.composition import Container, Readiness, Registry, SettingsResolver
from warpweft.core.context import (
    InvocationContext,
    current_correlation_id,
    report_progress,
    use_correlation_id,
)
from warpweft.core.errors import (
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
from warpweft.core.formats import Format
from warpweft.core.outcome import Outcome
from warpweft.runtime import App, AxisHandle, autodiscover, component, default_registry

__all__ = [
    "AComponent",
    "Action",
    "ActionParams",
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
    "Provider",
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
    "report_progress",
    "use_correlation_id",
]
