"""Dynamic configuration model, assembled at descriptor-build time.

A component cannot statically list ``retry``, ``cache``, ``timeout`` in a base
class - a third-party link could never add its own field then. So the full
configuration model is built at runtime from the component's own settings plus
the settings models of the known links, glued with ``pydantic.create_model``.

Static typing is lost by construction; the exported JSON Schema is the
compensation - it drives validation and editor autocompletion of config files.

Resulting shape::

    base_url: str            # the component's own field
    api_key: SecretStr       # the component's own field
    policy:
      chain: [concurrency, cache, circuit_breaker, retry, timeout]
      timeout: {...}         # the timeout link's settings model
      retry:   {...}         # the retry link's settings model
"""

from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, Field, create_model

from halyard.core.errors import ConfigurationError

#: Reserved field name the policy sub-model occupies on the config model.
POLICY_FIELD = "policy"


def build_policy_model(
    owner: str,
    default_chain: Sequence[str],
    link_models: Mapping[str, type[BaseModel]],
) -> type[BaseModel]:
    """Build the ``policy`` sub-model: a chain plus one field per known link.

    Links without a settings model still belong in ``chain`` (the order is a
    fixed contract), they simply get no settings sub-field.
    """
    fields: dict[str, Any] = {
        "chain": (list[str], Field(default=list(default_chain))),
    }
    for link, model in link_models.items():
        fields[link] = (model | None, Field(default=None))
    return create_model(f"{owner}_policy", **fields)


def build_config_model(
    owner: str,
    own_settings: type[BaseModel] | None,
    default_chain: Sequence[str],
    link_models: Mapping[str, type[BaseModel]],
) -> type[BaseModel]:
    """Assemble the full config model: the component's own fields + ``policy``.

    Raises :class:`ConfigurationError` if a component's own field would collide
    with the reserved ``policy`` name.
    """
    if own_settings is not None and POLICY_FIELD in own_settings.model_fields:
        raise ConfigurationError(
            f"component '{owner}' declares a settings field named '{POLICY_FIELD}', "
            f"which is reserved for the policy sub-model"
        )

    policy_model = build_policy_model(owner, default_chain, link_models)
    base: type[BaseModel] = own_settings if own_settings is not None else BaseModel
    extra: dict[str, Any] = {POLICY_FIELD: (policy_model, Field(default_factory=policy_model))}
    return create_model(f"{owner}_config", __base__=base, **extra)
