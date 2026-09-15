"""App facade: registration, autodiscovery, env config, lifecycle, lifespan."""

from types import SimpleNamespace
from typing import Any

from pydantic import BaseModel
import pytest

from halyard.core.component import AComponent, EmptySettings, invocable
from halyard.core.composition import Registry
from halyard.core.errors import ConfigurationError
from halyard.runtime import App, collect_env_config, component, default_registry

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


class GreeterSettings(BaseModel):
    greeting: str = "hello"
    volume: int = 1


class Greeter(AComponent[GreeterSettings, str, str]):
    @invocable
    async def greet(self, whom: str) -> str:
        return f"{self.settings.greeting} {whom} x{self.settings.volume}"


def fresh_app(**kwargs: Any) -> App:
    registry = Registry()
    registry.register(Greeter)
    return App(registry=registry, **kwargs)


# --- registration ------------------------------------------------------------


def test_module_level_component_registers_into_the_default_registry() -> None:
    @component
    class DefaultRegistered(AComponent[EmptySettings, None, None]):
        @invocable
        async def go(self) -> None: ...

    assert default_registry().get("default_registered") is DefaultRegistered


def test_app_component_decorator_targets_the_apps_own_registry() -> None:
    registry = Registry()
    app = App(registry=registry)

    @app.component
    class Isolated(AComponent[EmptySettings, None, None]):
        @invocable
        async def go(self) -> None: ...

    assert registry.get("isolated") is Isolated
    assert app.registry is registry
    assert "isolated" not in default_registry()


def test_autodiscover_imports_modules_and_skips_private_ones() -> None:
    app = App()  # default registry: the fixture package registers into it
    imported = app.autodiscover("sample_app")
    assert "sample_app.widgets" in imported
    assert all("_private" not in name for name in imported)
    assert "sample_widget" in default_registry()


def test_autodiscover_accepts_a_plain_module() -> None:
    app = App()
    assert app.autodiscover("sample_app.widgets") == ("sample_app.widgets",)


# --- configuration -----------------------------------------------------------


def test_env_values_override_config_per_field() -> None:
    app = fresh_app(
        config={"greeter": {"greeting": "hi", "volume": 2}},
        env_prefix="TESTAPP",
        environ={"TESTAPP_GREETER__VOLUME": "5"},
    )
    section = app.config_mapping()["greeter"]
    assert section == {"greeting": "hi", "volume": 5}  # env won volume, config kept greeting


def test_registered_but_unconfigured_component_defaults_to_empty_section() -> None:
    app = fresh_app()
    assert app.config_mapping() == {"greeter": {}}


def test_collect_env_config_shapes_nested_paths_and_json_values() -> None:
    env = {
        "MYAPP_GREETER__GREETING": "yo",  # plain string
        "MYAPP_GREETER__POLICY__RETRY__ATTEMPTS": "3",  # nested + json number
        "MYAPP_GREETER__POLICY__RETRY__JITTER": "false",  # json bool
        "MYAPP_DEBUG": "1",  # no '__': the app's own variable, ignored
        "OTHER_GREETER__X": "1",  # foreign prefix, ignored
    }
    config = collect_env_config(["greeter"], "MYAPP", env)
    assert config == {"greeter": {"greeting": "yo", "policy": {"retry": {"attempts": 3, "jitter": False}}}}


def test_env_var_for_unknown_component_is_a_configuration_error() -> None:
    with pytest.raises(ConfigurationError, match="unknown component 'ghost'"):
        collect_env_config(["greeter"], "MYAPP", {"MYAPP_GHOST__X": "1"})


def test_dashed_component_names_match_underscored_env_segments() -> None:
    config = collect_env_config(["my-svc"], "MYAPP", {"MYAPP_MY_SVC__RATE": "10"})
    assert config == {"my-svc": {"rate": 10}}


# --- lifecycle ---------------------------------------------------------------


async def test_run_starts_serves_and_stops() -> None:
    app = fresh_app(config={"greeter": {"greeting": "privet"}})
    async with app.run() as container:
        outcome = await app.invoke("greeter", "greet", whom="mir")
        assert outcome.value == "privet mir x1"
        assert container.started
    assert not container.started  # stopped on exit


async def test_typed_passthroughs() -> None:
    app = fresh_app()
    async with app.run():
        greeter = await app.get(Greeter)
        assert isinstance(greeter, Greeter)
        assert await app.proxy(Greeter).greet(whom="you") == "hello you x1"


async def test_container_property_requires_start() -> None:
    app = fresh_app()
    with pytest.raises(ConfigurationError, match="not started"):
        _ = app.container
    async with app.run():
        assert app.container.started
    await app.stop()  # second stop: no-op


async def test_start_is_idempotent() -> None:
    app = fresh_app()
    first = await app.start()
    second = await app.start()
    assert first is second
    await app.stop()


async def test_env_config_reaches_the_running_component() -> None:
    app = fresh_app(env_prefix="RTAPP", environ={"RTAPP_GREETER__GREETING": "salve"})
    async with app.run():
        assert await app.proxy(Greeter).greet(whom="munde") == "salve munde x1"


async def test_build_options_pass_through_to_the_container() -> None:
    app = fresh_app(framework_defaults={"volume": 7})
    async with app.run():
        assert app.container.resolved_settings("greeter")["volume"] == 7


# --- universal lifespan --------------------------------------------------------


async def test_lifespan_used_by_an_asgi_style_host() -> None:
    app = fresh_app()
    host = SimpleNamespace()  # whatever the framework passes is ignored

    async with app.lifespan(host):  # e.g. FastAPI(lifespan=app.lifespan)
        container = app.container
        assert container.started
        assert (await app.invoke("greeter", "greet", whom="web")).value == "hello web x1"
    assert not container.started  # stopped on shutdown


async def test_lifespan_works_standalone_without_a_host() -> None:
    app = fresh_app()
    async with app.lifespan():
        assert app.container.started
    with pytest.raises(ConfigurationError, match="not started"):
        _ = app.container


async def test_lifespan_stops_even_when_the_host_body_raises() -> None:
    app = fresh_app()
    with pytest.raises(RuntimeError, match="host blew up"):
        async with app.lifespan():
            saved = app.container
            raise RuntimeError("host blew up")
    assert not saved.started
