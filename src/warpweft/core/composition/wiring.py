"""Building a method's link chain from its config and effective policy.

Shared by the container and the testing helpers, so a test drives the *same*
chain production does. The order comes from the config's chain, the method's
effective policy restricts which links are allowed, and a link is active only
when it is implemented and has settings.
"""

from collections.abc import Mapping
import inspect
from typing import Any, get_type_hints

from pydantic import BaseModel

from warpweft.core.clock import Clock
from warpweft.core.component.policy import EffectivePolicy
from warpweft.core.component.settings import POLICY_FIELD
from warpweft.core.context import InvocationContext
from warpweft.core.errors import ErrorClassifier
from warpweft.core.outcome import Outcome
from warpweft.core.pipeline.chain import DEFAULT_ORDER
from warpweft.core.pipeline.interceptor import InterceptorFactory, Next

from .links import BUILTIN_LINK_BUILDERS


def link_settings(config: BaseModel, link: str, override: Mapping[str, Any]) -> BaseModel | None:
    """Resolve a link's settings from the config, applying a per-method override."""
    policy = getattr(config, POLICY_FIELD, None)
    base: BaseModel | None = getattr(policy, link, None) if policy is not None else None
    if base is None:
        return None
    if not override:
        return base
    return type(base).model_validate({**base.model_dump(), **override})


def active_links(config: BaseModel, policy: EffectivePolicy) -> list[tuple[str, BaseModel]]:
    """The ``(link name, settings)`` pairs active for a method, outermost first."""
    config_policy = getattr(config, POLICY_FIELD, None)
    config_chain = getattr(config_policy, "chain", None) or DEFAULT_ORDER
    allowed = set(policy.chain)
    result: list[tuple[str, BaseModel]] = []
    for link in config_chain:
        if link not in allowed or BUILTIN_LINK_BUILDERS.get(link) is None:
            continue
        settings = link_settings(config, link, policy.overrides.get(link, {}))
        if settings is None:
            continue
        result.append((link, settings))
    return result


def method_factories(
    config: BaseModel, policy: EffectivePolicy, clock: Clock, classifier: ErrorClassifier
) -> list[InterceptorFactory]:
    """The link factories for a method, outermost first."""
    return [BUILTIN_LINK_BUILDERS[link](settings, clock, classifier) for link, settings in active_links(config, policy)]


def make_base(instance: object, method_name: str) -> Next:
    """Wrap a bound method as a base call: bind arguments, inject context, wrap result.

    Arguments come from ``ctx.arguments``; if the method declares an
    ``InvocationContext`` parameter it receives the context; a raw return value
    is wrapped in an :class:`Outcome`.
    """
    method = getattr(instance, method_name)
    hints = get_type_hints(method)
    ctx_param = next(
        (name for name in inspect.signature(method).parameters if hints.get(name) is InvocationContext),
        None,
    )

    async def base(ctx: InvocationContext) -> Outcome[Any]:
        kwargs = dict(ctx.arguments or {})
        if ctx_param is not None:
            kwargs[ctx_param] = ctx
        result = await method(**kwargs)
        return result if isinstance(result, Outcome) else Outcome(value=result)

    return base
