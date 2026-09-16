"""Build an MCP server from an app's ``@tool`` invocables.

Discovery, the ``list_tools`` / ``call_tool`` handlers and the transport
adapters live here. Tool logic is transport-agnostic: :func:`build_server`
returns a wired server; :func:`run_stdio` drives it over stdio (a local
subprocess host such as Claude Desktop or an IDE).

Each tool is one ``@tool``-marked invocable. A call is routed through
``container.invoke``, so it runs the component's full policy chain and
telemetry; the result is serialized against the invocable's output schema
(secrets masked) and returned as both structured and text content.
"""

from dataclasses import dataclass
import inspect
import json
from typing import Any

from mcp.server.lowlevel.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as mt
from pydantic import ValidationError

from warpweft.core.component import InvocableSpec, describe
from warpweft.core.errors import FrameworkError
from warpweft.runtime import App

from .schema import tool_input_schema
from .tool import ToolMeta, is_tool, tool_meta


@dataclass(frozen=True)
class ToolBinding:
    """One exposed tool: its MCP name and how to run it."""

    name: str
    component: str
    method: str
    meta: ToolMeta
    spec: InvocableSpec


def _tool_name(component: str, method: str, meta: ToolMeta) -> str:
    # MCP tool names allow [A-Za-z0-9_-] but not '.', so join with '__'.
    return meta.name or f"{component}__{method}"


def collect_tools(app: App) -> list[ToolBinding]:
    """Find every ``@tool`` invocable across the app's registered components.

    Raises if a method is marked ``@tool`` but is not an ``@invocable`` (a
    tool must be a pipeline entry point), or if two tools resolve to the same
    MCP name.
    """
    bindings: list[ToolBinding] = []
    seen: dict[str, str] = {}
    for component in sorted(app.registry.names()):
        cls = app.registry.get(component)
        descriptor = describe(cls)
        for method_name, member in inspect.getmembers(cls, predicate=is_tool):
            if method_name not in descriptor.invocables:
                raise FrameworkError(f"'{component}.{method_name}' is marked @tool but is not @invocable")
            meta = tool_meta(member)
            name = _tool_name(component, method_name, meta)
            if name in seen:
                raise FrameworkError(f"duplicate tool name '{name}' from {seen[name]} and {component}.{method_name}")
            seen[name] = f"{component}.{method_name}"
            bindings.append(
                ToolBinding(
                    name=name,
                    component=component,
                    method=method_name,
                    meta=meta,
                    spec=descriptor.invocables[method_name],
                )
            )
    return bindings


def _annotations(meta: ToolMeta) -> mt.ToolAnnotations | None:
    hints = {
        "title": meta.title,
        "read_only_hint": meta.read_only,
        "destructive_hint": meta.destructive,
        "idempotent_hint": meta.idempotent,
        "open_world_hint": meta.open_world,
    }
    present = {k: v for k, v in hints.items() if v is not None}
    return mt.ToolAnnotations(**present) if present else None


def _describe_tool(cls: type, binding: ToolBinding) -> mt.Tool:
    method = getattr(cls, binding.method)
    description = binding.meta.description or (inspect.getdoc(method) or None)
    output_schema = binding.spec.output_json_schema()
    return mt.Tool(
        name=binding.name,
        title=binding.meta.title,
        description=description,
        input_schema=tool_input_schema(binding.spec.input_model),
        # MCP output schemas must be object schemas; advertise only then.
        output_schema=output_schema if output_schema.get("type") == "object" else None,
        annotations=_annotations(binding.meta),
    )


def _serialize(binding: ToolBinding, value: Any) -> Any:
    return binding.spec.output_adapter.dump_python(value, mode="json")


def build_server(app: App, *, name: str = "warpweft", version: str = "0") -> Server[Any]:
    """Wire an MCP server exposing the app's tools. The app must be started."""
    bindings = {b.name: b for b in collect_tools(app)}
    classes = {name: app.registry.get(name) for name in app.registry.names()}

    async def on_list_tools(ctx: Any, params: Any) -> mt.ListToolsResult:
        tools = [_describe_tool(classes[b.component], b) for b in bindings.values()]
        return mt.ListToolsResult(tools=tools)

    async def on_call_tool(ctx: Any, params: mt.CallToolRequestParams) -> mt.CallToolResult:
        binding = bindings.get(params.name)
        if binding is None:
            unknown = mt.TextContent(type="text", text=f"unknown tool '{params.name}'")
            return mt.CallToolResult(content=[unknown], is_error=True)
        # Validate/coerce the LLM-supplied arguments against the invocable's
        # input model (this is where field formats are enforced), then pass the
        # coerced values on. The container itself does not re-validate.
        try:
            model = binding.spec.input_model.model_validate(params.arguments or {})
        except ValidationError as exc:
            return mt.CallToolResult(content=[mt.TextContent(type="text", text=str(exc))], is_error=True)
        kwargs = {field: getattr(model, field) for field in type(model).model_fields}
        try:
            outcome = await app.container.invoke(binding.component, binding.method, **kwargs)
        except FrameworkError as exc:
            return mt.CallToolResult(content=[mt.TextContent(type="text", text=str(exc))], is_error=True)

        serialized = _serialize(binding, outcome.value)
        text = serialized if isinstance(serialized, str) else json.dumps(serialized)
        return mt.CallToolResult(
            content=[mt.TextContent(type="text", text=text)],
            structured_content=serialized if isinstance(serialized, dict) else None,
            meta={"warpweft.source": outcome.source, "warpweft.degraded": outcome.degraded},
        )

    return Server(name, version=version, on_list_tools=on_list_tools, on_call_tool=on_call_tool)


async def run_stdio(
    app: App, *, name: str = "warpweft", version: str = "0"
) -> None:  # pragma: no cover - needs real stdio
    """Start the app and serve its tools over stdio until the stream closes."""
    async with app.run():
        server = build_server(app, name=name, version=version)
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
