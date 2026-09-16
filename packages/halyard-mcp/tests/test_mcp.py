"""halyard-mcp: tool discovery, schemas, and end-to-end call routing."""

from typing import Any

from pydantic import BaseModel, SecretStr
import pytest

from halyard.core.component import AComponent, EmptySettings, invocable
from halyard.core.composition import Registry
from halyard.core.errors import FrameworkError, PermanentError, TransientError
from halyard.mcp import collect_tools, tool
from halyard.runtime import App

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


class Doc(BaseModel):
    id: str
    score: float


class Search(AComponent[EmptySettings, str, list[Doc]]):
    name = "search"

    @tool(description="Search the index.", read_only=True)
    @invocable
    async def query(self, text: str, limit: int = 10) -> list[Doc]:
        return [Doc(id=f"{text}-{i}", score=1.0 / (i + 1)) for i in range(1)]

    @invocable
    async def _refresh(self) -> None:  # not a tool
        return None


class Profile(BaseModel):
    name: str
    token: SecretStr


class Accounts(AComponent[EmptySettings, str, Profile]):
    name = "accounts"

    @tool  # bare; description from the docstring
    @invocable
    async def get(self, user_id: str) -> Profile:
        """Return a user profile."""
        return Profile(name=f"user-{user_id}", token=SecretStr("s3cr3t"))


def app_with(*classes: type[AComponent[Any, Any, Any]]) -> App:
    reg = Registry()
    for cls in classes:
        reg.register(cls)
    return App(registry=reg)


# --- discovery ---------------------------------------------------------------


def test_collect_finds_only_tool_marked_invocables() -> None:
    bindings = collect_tools(app_with(Search))
    assert [(b.name, b.component, b.method) for b in bindings] == [("search__query", "search", "query")]


def test_collect_uses_name_override() -> None:
    class Named(AComponent[EmptySettings, None, str]):
        name = "svc"

        @tool(name="do_the_thing")
        @invocable
        async def run(self) -> str:
            return "ok"

    (binding,) = collect_tools(app_with(Named))
    assert binding.name == "do_the_thing"


def test_tool_on_non_invocable_is_rejected() -> None:
    class Bad(AComponent[EmptySettings, None, str]):
        name = "bad"

        @invocable
        async def real(self) -> str:
            return "ok"

        @tool  # marked tool but NOT invocable
        async def fake(self) -> str:
            return "no"

    with pytest.raises(FrameworkError, match="marked @tool but is not @invocable"):
        collect_tools(app_with(Bad))


def test_duplicate_tool_names_are_rejected() -> None:
    class A(AComponent[EmptySettings, None, str]):
        name = "a"

        @tool(name="dup")
        @invocable
        async def x(self) -> str:
            return "1"

    class B(AComponent[EmptySettings, None, str]):
        name = "b"

        @tool(name="dup")
        @invocable
        async def y(self) -> str:
            return "2"

    with pytest.raises(FrameworkError, match="duplicate tool name 'dup'"):
        collect_tools(app_with(A, B))


# --- list_tools --------------------------------------------------------------


async def test_list_tools_exposes_schema_and_annotations(connect) -> None:
    async with connect(app_with(Search)) as client:
        result = await client.list_tools()
    (tool_def,) = result.tools
    assert tool_def.name == "search__query"
    assert tool_def.description == "Search the index."
    assert set(tool_def.input_schema["properties"]) == {"text", "limit"}
    assert tool_def.annotations is not None
    assert tool_def.annotations.read_only_hint is True


async def test_description_falls_back_to_the_docstring(connect) -> None:
    async with connect(app_with(Accounts)) as client:
        result = await client.list_tools()
    (tool_def,) = result.tools
    assert tool_def.description == "Return a user profile."


async def test_object_return_advertises_output_schema(connect) -> None:
    async with connect(app_with(Accounts)) as client:
        result = await client.list_tools()
    (tool_def,) = result.tools
    assert tool_def.output_schema is not None
    assert tool_def.output_schema["type"] == "object"


async def test_non_object_return_has_no_output_schema(connect) -> None:
    async with connect(app_with(Search)) as client:
        result = await client.list_tools()
    (tool_def,) = result.tools  # returns a list -> no object output schema
    assert tool_def.output_schema is None


# --- call_tool ---------------------------------------------------------------


async def test_call_returns_text_content(connect) -> None:
    async with connect(app_with(Search)) as client:
        result = await client.call_tool("search__query", {"text": "sre"})
    assert result.is_error is False
    assert "sre-0" in result.content[0].text


async def test_object_call_returns_structured_content_and_masks_secrets(connect) -> None:
    async with connect(app_with(Accounts)) as client:
        result = await client.call_tool("accounts__get", {"user_id": "42"})
    assert result.structured_content == {"name": "user-42", "token": "**********"}
    assert "s3cr3t" not in result.content[0].text  # secret never leaks


async def test_call_reports_outcome_metadata(connect) -> None:
    async with connect(app_with(Search)) as client:
        result = await client.call_tool("search__query", {"text": "x"})
    assert result.meta is not None
    assert result.meta["halyard.source"] == "live"
    assert result.meta["halyard.degraded"] is False


async def test_unknown_tool_is_an_error(connect) -> None:
    async with connect(app_with(Search)) as client:
        result = await client.call_tool("search__ghost", {})
    assert result.is_error is True
    assert "unknown tool" in result.content[0].text


async def test_permanent_error_becomes_a_tool_error(connect) -> None:
    class Boom(AComponent[EmptySettings, None, str]):
        name = "boom"

        @tool
        @invocable
        async def go(self) -> str:
            raise PermanentError("bad request")

    async with connect(app_with(Boom)) as client:
        result = await client.call_tool("boom__go", {})
    assert result.is_error is True
    assert "bad request" in result.content[0].text


async def test_call_runs_through_the_policy_chain(connect) -> None:
    calls = {"n": 0}

    class Flaky(AComponent[EmptySettings, None, str]):
        name = "flaky"

        @tool
        @invocable
        async def fetch(self) -> str:
            calls["n"] += 1
            if calls["n"] < 3:
                raise TransientError("warming up")
            return "ok"

    reg = Registry()
    reg.register(Flaky)
    app = App(
        registry=reg,
        config={"flaky": {"policy": {"retry": {"attempts": 3, "base_delay": 0.0, "max_delay": 1.0}}}},
    )
    async with connect(app) as client:
        result = await client.call_tool("flaky__fetch", {})
    assert result.is_error is False
    assert calls["n"] == 3  # retry ran under the tool call
