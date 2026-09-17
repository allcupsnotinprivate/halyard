"""Build an MCP server from an app's ``@tool`` invocables.

Discovery, the ``list_tools`` / ``call_tool`` handlers and the transport
adapters live here. Tool logic is transport-agnostic: `build_server`
returns a wired server; `run_stdio` drives it over stdio (a local
subprocess host such as Claude Desktop or an IDE).

Each tool is one ``@tool``-marked invocable. A call is routed through
``container.invoke``, so it runs the component's full policy chain and
telemetry; the result is serialized against the invocable's output schema
(secrets masked) and returned as both structured and text content.
"""

from collections.abc import Collection
from dataclasses import dataclass
from fnmatch import fnmatchcase
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


def _filter_bindings(
    bindings: list[ToolBinding],
    *,
    tags: Collection[str] | None,
    include: Collection[str] | None,
    exclude: Collection[str] | None,
) -> list[ToolBinding]:
    """Narrow the tool set: ``tags`` (any match) -> ``include`` -> ``exclude``.

    Validation is strict so a typo cannot silently expose the wrong set: every
    requested tag must be declared by some tool, every include/exclude pattern
    must match some tool name (both checked against the *unfiltered* set), and
    the surviving set must not be empty.
    """
    if tags is None and include is None and exclude is None:
        return bindings
    all_names = sorted(b.name for b in bindings)
    all_tags = {t for b in bindings for t in b.meta.tags}
    if tags is not None:
        unknown = sorted(set(tags) - all_tags)
        if unknown:
            raise FrameworkError(f"no tool declares tag(s) {unknown}; declared tags: {sorted(all_tags)}")
    for label, patterns in (("include", include), ("exclude", exclude)):
        for pattern in sorted(patterns or ()):
            if not any(fnmatchcase(name, pattern) for name in all_names):
                raise FrameworkError(f"{label} pattern '{pattern}' matches no tool; tools: {all_names}")
    selected = bindings
    if tags is not None:
        wanted = frozenset(tags)
        selected = [b for b in selected if wanted & b.meta.tags]
    if include is not None:
        selected = [b for b in selected if any(fnmatchcase(b.name, p) for p in include)]
    if exclude is not None:
        selected = [b for b in selected if not any(fnmatchcase(b.name, p) for p in exclude)]
    if not selected:
        raise FrameworkError("tool filter leaves no tools to expose")
    return selected


def collect_tools(
    app: App,
    *,
    tags: Collection[str] | None = None,
    include: Collection[str] | None = None,
    exclude: Collection[str] | None = None,
) -> list[ToolBinding]:
    """Find every ``@tool`` invocable across the app's registered components.

    Raises if a method is marked ``@tool`` but is not an ``@invocable`` (a
    tool must be a pipeline entry point), or if two tools resolve to the same
    MCP name.

    The keyword arguments narrow the set, applied in order:

    - ``tags`` - keep tools carrying at least one of these tags. A tool with
      no tags never passes a tag filter, so tagging works as a whitelist.
    - ``include`` - keep only these MCP tool names (``fnmatch`` globs allowed,
      e.g. ``"search__*"``).
    - ``exclude`` - drop these names (globs allowed); wins over ``include``.

    A tag no tool declares, a pattern matching no tool, or a filter leaving
    nothing to expose is a `FrameworkError` - a typo should fail loudly, not
    quietly serve the wrong tools.
    """
    bindings: list[ToolBinding] = []
    seen: dict[str, str] = {}
    for component in sorted(app.registry.names()):
        cls = app.registry.get(component)
        descriptor = describe(cls)
        tools = inspect.getmembers(cls, predicate=is_tool)
        if not cls.entrypoint:
            # A non-entry-point component (infrastructure) is never a tool.
            if tools:
                raise FrameworkError(f"component '{component}' is not an entry point but declares @tool methods")
            continue
        for method_name, member in tools:
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
    return _filter_bindings(bindings, tags=tags, include=include, exclude=exclude)


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


def build_server(
    app: App,
    *,
    name: str = "warpweft",
    version: str = "0",
    tags: Collection[str] | None = None,
    include: Collection[str] | None = None,
    exclude: Collection[str] | None = None,
) -> Server[Any]:
    """Wire an MCP server exposing the app's tools. The app must be started.

    ``tags``/``include``/``exclude`` narrow which tools are served (see
    `collect_tools`), so one app can back several servers with different
    tool sets - e.g. ``tags={"public"}`` for an assistant, no filter for an
    operator console.
    """
    bindings = {b.name: b for b in collect_tools(app, tags=tags, include=include, exclude=exclude)}
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
    app: App,
    *,
    name: str = "warpweft",
    version: str = "0",
    tags: Collection[str] | None = None,
    include: Collection[str] | None = None,
    exclude: Collection[str] | None = None,
) -> None:  # pragma: no cover - needs real stdio
    """Start the app and serve its tools over stdio until the stream closes."""
    async with app.run():
        server = build_server(app, name=name, version=version, tags=tags, include=include, exclude=exclude)
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
