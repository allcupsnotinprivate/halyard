"""Composition: type registry, dependency graph, and the instance container."""

from .config import DictSettingsResolver, SettingsResolver, assemble_config, deep_merge
from .container import Container
from .endpoint import ENDPOINT_AXIS, endpoint_axis, use_endpoint
from .graph import DependencyGraph, GraphNode
from .health import Readiness, aggregate_readiness
from .introspection import (
    BreakerSnapshot,
    ConcurrencySnapshot,
    MethodExplanation,
    RuntimeSnapshot,
)
from .links import BUILTIN_LINK_BUILDERS
from .registry import ENTRY_POINT_GROUP, Registry

__all__ = [
    "BUILTIN_LINK_BUILDERS",
    "ENDPOINT_AXIS",
    "ENTRY_POINT_GROUP",
    "BreakerSnapshot",
    "ConcurrencySnapshot",
    "Container",
    "DependencyGraph",
    "DictSettingsResolver",
    "GraphNode",
    "MethodExplanation",
    "Readiness",
    "Registry",
    "RuntimeSnapshot",
    "SettingsResolver",
    "aggregate_readiness",
    "assemble_config",
    "deep_merge",
    "endpoint_axis",
    "use_endpoint",
]
