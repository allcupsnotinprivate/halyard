"""describe(): discovery, IO schemas, effective policies, config model, caching."""

from pydantic import BaseModel
import pytest

from halyard.core.component import (
    AComponent,
    Criticality,
    Descriptor,
    EmptySettings,
    Policy,
    describe,
    invocable,
)
from halyard.core.pipeline.builtin.retry import RetrySettings
from halyard.core.pipeline.chain import DEFAULT_ORDER

pytestmark = pytest.mark.unit


class Doc(BaseModel):
    id: str
    score: float


class SearchSettings(BaseModel):
    base_url: str


class Search(AComponent[SearchSettings, str, list[Doc]]):
    name = "search"
    version = "1"
    dependencies = ("embedder",)
    criticality = Criticality.OPTIONAL

    @invocable
    async def query(self, text: str, limit: int = 10) -> list[Doc]:
        return []

    @invocable(policy=Policy(chain=("timeout",)))
    async def probe(self) -> bool:
        return True


def test_descriptor_basic_metadata() -> None:
    d = describe(Search)
    assert isinstance(d, Descriptor)
    assert d.identity.uid == "search@1"
    assert d.settings_model is SearchSettings
    assert d.dependencies == ("embedder",)
    assert d.criticality is Criticality.OPTIONAL


def test_invocables_are_discovered() -> None:
    d = describe(Search)
    assert set(d.invocables) == {"query", "probe"}


def test_io_schemas_are_derived_from_annotations() -> None:
    d = describe(Search)
    q = d.invocables["query"]
    assert set(q.input_json_schema()["properties"]) == {"text", "limit"}
    assert q.output_json_schema()["type"] == "array"


def test_effective_policy_per_method() -> None:
    d = describe(Search)
    assert d.invocables["query"].policy.chain == DEFAULT_ORDER  # inherited default
    assert d.invocables["probe"].policy.chain == ("timeout",)  # method override


def test_config_model_combines_own_and_policy() -> None:
    d = describe(Search)
    assert set(d.config_model.model_fields) == {"base_url", "policy"}
    schema = d.config_json_schema()
    assert "base_url" in schema["properties"]
    assert "policy" in schema["properties"]


def test_descriptor_is_cached_per_type() -> None:
    assert describe(Search) is describe(Search)


def test_rebuild_forces_a_fresh_descriptor() -> None:
    first = describe(Search)
    second = describe(Search, rebuild=True)
    assert first is not second


def test_custom_link_models_shape_the_policy() -> None:
    d = describe(Search, link_models={"retry": RetrySettings}, rebuild=True)
    policy_fields = d.config_model.model_fields["policy"].annotation.model_fields  # type: ignore[union-attr]
    assert "retry" in policy_fields
    assert "timeout" not in policy_fields


def test_component_without_name_is_rejected() -> None:
    class Nameless(AComponent[EmptySettings, None, None]):
        @invocable
        async def go(self) -> None: ...

    with pytest.raises(ValueError, match="name"):
        describe(Nameless)


def test_component_without_invocables_is_rejected() -> None:
    class Empty(AComponent[EmptySettings, None, None]):
        name = "empty"

    with pytest.raises(ValueError, match="no @invocable"):
        describe(Empty)


def test_empty_settings_component_config_has_only_policy() -> None:
    class Ping(AComponent[EmptySettings, None, None]):
        name = "ping"

        @invocable
        async def ping(self) -> bool:
            return True

    d = describe(Ping)
    assert d.settings_model is EmptySettings
    assert set(d.config_model.model_fields) == {"policy"}
