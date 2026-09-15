"""Environment-based configuration for components.

Environment variables map onto the deployment config by convention::

    <PREFIX>_<COMPONENT>__<FIELD>[__<NESTED>...] = value

    MYAPP_PROFILES__BASE_URL=https://api.example.com
    MYAPP_PROFILES__POLICY__RETRY__ATTEMPTS=3

The component segment is the component name uppercased (``-`` and ``_`` both
match ``_``). Values are parsed as JSON when possible (numbers, booleans,
lists, objects) and kept as strings otherwise; validation and type coercion
stay with the core's config assembly, which also reports good errors.

Variables under the prefix *without* a ``__`` (e.g. ``MYAPP_DEBUG``) are
ignored - they are the application's own. A ``__``-shaped variable naming an
unknown component is an error: that is almost always a typo.
"""

from collections.abc import Iterable, Mapping
import json
import os
from typing import Any

from halyard.core.errors import ConfigurationError


def _parse_value(raw: str) -> Any:
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def _normalize(name: str) -> str:
    return name.replace("-", "_").upper()


def collect_env_config(
    component_names: Iterable[str],
    prefix: str,
    environ: Mapping[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Build a ``{component: config}`` mapping from prefixed env variables."""
    environ = os.environ if environ is None else environ
    by_segment = {_normalize(name): name for name in component_names}
    marker = f"{prefix}_"

    result: dict[str, dict[str, Any]] = {}
    for key, raw in environ.items():
        if not key.startswith(marker):
            continue
        rest = key[len(marker) :]
        if "__" not in rest:
            continue  # the application's own variable, not component config
        segment, path = rest.split("__", 1)
        name = by_segment.get(segment)
        if name is None:
            raise ConfigurationError(f"environment variable '{key}' names unknown component '{segment.lower()}'")
        node = result.setdefault(name, {})
        parts = [part.lower() for part in path.split("__")]
        for part in parts[:-1]:
            child = node.get(part)
            if not isinstance(child, dict):
                child = {}
                node[part] = child
            node = child
        node[parts[-1]] = _parse_value(raw)
    return result
