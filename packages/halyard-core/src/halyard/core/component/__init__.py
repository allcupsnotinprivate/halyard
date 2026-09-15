"""Component contract: base class, invocable methods, and derived descriptors."""

from .component import (
    AComponent,
    EmptySettings,
    Lifetime,
    component_dependencies,
    dependency_annotations,
    settings_model_of,
)
from .descriptor import BUILTIN_LINK_MODELS, Descriptor, describe
from .health import Health, HealthStatus
from .invocable import InvocableSpec, invocable, is_invocable, policy_override
from .policy import DEFAULT_POLICY, Criticality, EffectivePolicy, Policy, resolve_policy
from .settings import build_config_model, build_policy_model

__all__ = [
    "BUILTIN_LINK_MODELS",
    "DEFAULT_POLICY",
    "AComponent",
    "Criticality",
    "Descriptor",
    "EffectivePolicy",
    "EmptySettings",
    "Health",
    "HealthStatus",
    "InvocableSpec",
    "Lifetime",
    "Policy",
    "build_config_model",
    "build_policy_model",
    "component_dependencies",
    "dependency_annotations",
    "describe",
    "invocable",
    "is_invocable",
    "policy_override",
    "resolve_policy",
    "settings_model_of",
]
