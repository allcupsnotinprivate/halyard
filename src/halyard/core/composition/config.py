"""Configuration assembly: layered sources, per-field merge, provenance.

A component's configuration is merged from four sources, each overriding the
previous **field by field** (never replacing a whole object):

1. framework defaults,
2. the component author's defaults,
3. the deployment config,
4. the per-slice override (from a :class:`SettingsResolver`).

Merging records where every leaf value came from (its *provenance*), which
powers both good error messages (naming the offending field, component and
source) and introspection ("where did this setting come from?").

The per-slice resolver is a swappable protocol: production reads a database,
tests read a dict. The core only asks "settings for this key" and caches the
assembled result upstream.
"""

from collections.abc import Mapping
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

from halyard.core.axes import ScopeKey
from halyard.core.errors import ConfigurationError

#: Maps a dotted field path to the name of the source that set it.
Provenance = dict[str, str]

SOURCE_FRAMEWORK = "framework defaults"
SOURCE_COMPONENT = "component defaults"
SOURCE_DEPLOYMENT = "deployment config"
SOURCE_SLICE = "slice override"


class SettingsResolver(Protocol):
    """Supplies the per-slice configuration override for a component instance."""

    def resolve(self, component: str, scope_key: ScopeKey) -> Mapping[str, Any]:
        """Return the override for ``(component, scope_key)`` (empty if none)."""
        ...


class DictSettingsResolver:
    """A resolver backed by an in-memory ``{(component, scope_key): dict}`` map."""

    def __init__(self, overrides: Mapping[tuple[str, ScopeKey], Mapping[str, Any]] | None = None) -> None:
        self._overrides = dict(overrides or {})

    def resolve(self, component: str, scope_key: ScopeKey) -> Mapping[str, Any]:
        override = self._overrides.get((component, scope_key))
        return {} if override is None else override


def deep_merge(layers: list[tuple[str, Mapping[str, Any]]]) -> tuple[dict[str, Any], Provenance]:
    """Merge ``(source, mapping)`` layers in order; later layers win per leaf.

    Nested mappings are merged recursively rather than replaced. Every scalar
    leaf's source is recorded in the returned provenance by dotted path.
    """
    merged: dict[str, Any] = {}
    provenance: Provenance = {}

    def merge_into(dst: dict[str, Any], src: Mapping[str, Any], source: str, prefix: str) -> None:
        for key, value in src.items():
            path = f"{prefix}{key}"
            if isinstance(value, Mapping):
                node = dst.get(key)
                if not isinstance(node, dict):
                    node = {}
                    dst[key] = node
                merge_into(node, value, source, f"{path}.")
            else:
                dst[key] = value
                provenance[path] = source

    for source, layer in layers:
        merge_into(merged, layer, source, "")
    return merged, provenance


def assemble_config(
    component: str,
    config_model: type[BaseModel],
    layers: list[tuple[str, Mapping[str, Any]]],
) -> tuple[BaseModel, Provenance]:
    """Merge the layers and validate against ``config_model``.

    On a validation error, raises a :class:`ConfigurationError` naming the
    component, the full field path, and the source the value came from - so
    debugging a config never means guessing.
    """
    merged, provenance = deep_merge(layers)
    try:
        config = config_model.model_validate(merged)
    except ValidationError as exc:
        raise _describe_error(component, exc, provenance) from exc
    return config, provenance


def _describe_error(component: str, exc: ValidationError, provenance: Provenance) -> ConfigurationError:
    error = exc.errors()[0]
    path = ".".join(str(part) for part in error["loc"])
    source = provenance.get(path, "(unset)")
    return ConfigurationError(f"invalid config for component '{component}' at '{path}' (from {source}): {error['msg']}")
