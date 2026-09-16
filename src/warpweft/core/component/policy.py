"""Policy: which links wrap a call, in what order, with what overrides.

Policy is attached to a *method*, not to a component: ``search()`` and
``health()`` want different chains - health must never be retried or tripped
by a circuit breaker. A method's policy overrides the component's, which
overrides the framework default.

This module only models and resolves policy. Turning a resolved policy into a
running chain of link instances happens where the pipeline is wired.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from warpweft.core.pipeline.chain import DEFAULT_ORDER


class Criticality(StrEnum):
    """Whether the system can start and stay ready without this component."""

    REQUIRED = "required"
    OPTIONAL = "optional"


@dataclass(frozen=True)
class Policy:
    """A (partial) policy: an optional link order plus per-link setting overrides.

    ``chain`` of ``None`` means "inherit"; a tuple pins the exact links,
    outermost first. ``overrides`` maps a link name to a dict of setting
    values, validated against that link's settings model where the config is
    assembled - not here.
    """

    chain: tuple[str, ...] | None = None
    overrides: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)


#: The framework default: the fixed full-set order, no overrides.
DEFAULT_POLICY = Policy(chain=DEFAULT_ORDER)


@dataclass(frozen=True)
class EffectivePolicy:
    """A fully resolved policy: a concrete chain and merged overrides."""

    chain: tuple[str, ...]
    overrides: Mapping[str, Mapping[str, Any]]


def resolve_policy(method: Policy | None, component: Policy | None) -> EffectivePolicy:
    """Resolve method over component over framework default.

    ``chain`` takes the first pinned one (method, then component, then default).
    ``overrides`` are layered per link: default, then component, then method,
    each later layer winning field by field.
    """
    layers = [DEFAULT_POLICY, component, method]

    chain: tuple[str, ...] = DEFAULT_ORDER
    for layer in layers:
        if layer is not None and layer.chain is not None:
            chain = layer.chain

    merged: dict[str, dict[str, Any]] = {}
    for layer in layers:
        if layer is None:
            continue
        for link, values in layer.overrides.items():
            merged.setdefault(link, {}).update(values)

    return EffectivePolicy(chain=chain, overrides=merged)
