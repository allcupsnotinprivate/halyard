"""Composition: type registry, dependency graph, and the instance container."""

from .container import Container
from .endpoint import ENDPOINT_AXIS, endpoint_axis, use_endpoint
from .graph import DependencyGraph, GraphNode
from .health import Readiness, aggregate_readiness
from .links import BUILTIN_LINK_BUILDERS
from .registry import ENTRY_POINT_GROUP, Registry

__all__ = [
    "BUILTIN_LINK_BUILDERS",
    "ENDPOINT_AXIS",
    "ENTRY_POINT_GROUP",
    "Container",
    "DependencyGraph",
    "GraphNode",
    "Readiness",
    "Registry",
    "aggregate_readiness",
    "endpoint_axis",
    "use_endpoint",
]
