"""Reading config layers with pydantic-settings, kept as raw dicts.

pydantic-settings' source classes are used only as *readers*: each one turns a
place (the environment, a .env file, a config file) into a
``{component: {field: ...}}`` dict. The dicts are then merged and validated by
the core's config assembly, so provenance and source-named errors survive - we
do not hand the whole thing to a single BaseSettings, which would lose them.

A dynamic outer model (one field per component, typed by its config model)
gives the sources the nested-field structure they need for the ``__`` env
delimiter and for parsing files.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel, create_model
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    EnvSettingsSource,
    JsonConfigSettingsSource,
    PydanticBaseSettingsSource,
    TomlConfigSettingsSource,
)

from warpweft.core.errors import ConfigurationError

ConfigModels = Mapping[str, type[BaseModel]]


def _outer_model(config_models: ConfigModels) -> type[BaseSettings]:
    fields: dict[str, Any] = {name: (model | None, None) for name, model in config_models.items()}
    return create_model("WarpweftAppConfig", __base__=BaseSettings, **fields)


def _clean(raw: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Keep only components that a source actually provided a mapping for."""
    return {name: dict(section) for name, section in raw.items() if isinstance(section, Mapping)}


def _read(source: PydanticBaseSettingsSource) -> dict[str, dict[str, Any]]:
    return _clean(source())


def read_env(config_models: ConfigModels, prefix: str) -> dict[str, dict[str, Any]]:
    """Component config from environment variables (``PREFIX_COMPONENT__FIELD``)."""
    outer = _outer_model(config_models)
    return _read(EnvSettingsSource(outer, env_prefix=f"{prefix}_", env_nested_delimiter="__"))


def read_dotenv(config_models: ConfigModels, prefix: str, path: str | Path) -> dict[str, dict[str, Any]]:
    """Component config from a ``.env`` file, same convention as the environment."""
    outer = _outer_model(config_models)
    return _read(DotEnvSettingsSource(outer, env_file=path, env_prefix=f"{prefix}_", env_nested_delimiter="__"))


def read_file(config_models: ConfigModels, path: str | Path) -> dict[str, dict[str, Any]]:
    """Component config from a ``.toml`` / ``.json`` / ``.yaml`` file."""
    outer = _outer_model(config_models)
    file = Path(path)
    suffix = file.suffix
    if suffix == ".toml":
        return _read(TomlConfigSettingsSource(outer, toml_file=file))
    if suffix == ".json":
        return _read(JsonConfigSettingsSource(outer, json_file=file))
    if suffix in (".yaml", ".yml"):
        try:
            from pydantic_settings import YamlConfigSettingsSource
        except ImportError as exc:  # pragma: no cover - exercised only without the extra
            raise ConfigurationError("YAML config requires the 'yaml' extra: pip install warpweft[yaml]") from exc
        return _read(YamlConfigSettingsSource(outer, yaml_file=file))
    raise ConfigurationError(f"unsupported config file '{file}': expected .toml, .json, .yaml or .yml")
