# MCP tools

The `mcp` extra (`pip install warpweft[mcp]`) exposes a component's invocables as [Model Context
Protocol](https://modelcontextprotocol.io) tools. It is a projection, not a new
component type: a tool **is** an `@invocable` method that you additionally mark
with `@tool`. Every tool call is routed through `container.invoke`, so it runs
the component's full policy chain (retry, cache, breaker) and telemetry for
free. `@tool` lives in this package, so the core never learns about MCP.

## Marking a tool

```python
from warpweft import AComponent, invocable
from warpweft.mcp import tool


class Weather(AComponent[WeatherSettings, str, Forecast]):
    @tool(description="Get the forecast for a city.", read_only=True)
    @invocable
    async def forecast(self, city: str) -> Forecast: ...

    @invocable  # no @tool -> never exposed to an LLM
    async def _refresh(self) -> None: ...
```

Exposure is opt-in: only `@tool`-marked invocables become tools, so health
checks and internal helpers stay private. `@tool` accepts a `name`/`title`
override, a `description` (else the method docstring is used), and the MCP
annotation hints `read_only`, `destructive`, `idempotent`, `open_world`. A
`@tool` on a method that is not `@invocable` is rejected when the server is
built.

## Serving

```python
from warpweft.mcp import run_stdio

anyio.run(run_stdio, app)  # local host (Claude Desktop, an IDE)
```

`run_stdio` starts the app, serves its tools over stdio, and stops the app when
the stream closes. For programmatic use (or a future HTTP transport),
`build_server(app)` returns a transport-agnostic MCP server.

## The tool contract

Per tool, derived from the invocable's descriptor:

- **name** - `component__method` (MCP names disallow `.`) or the `name` override.
- **description** - the `@tool` description, else the method docstring.
- **inputSchema** - the method's input JSON Schema, with read-only/computed
  fields dropped (a model does not fill those in). Parameters annotated with a
  field format (`warpweft.formats`, e.g. `host: Ipv4`) carry the `format`
  keyword, and the arguments an LLM supplies are validated against the input
  model before the call - an invalid value comes back as a tool error.
- **outputSchema** - the return type's JSON Schema, advertised only when it is
  an object (per the MCP spec).
- **annotations** - the hint flags above.

## Results

A tool call returns the invocable's `Outcome`, serialized against the output
schema in JSON mode - so `SecretStr` fields are masked and enums/dates become
primitives. The result is returned as text content, plus `structuredContent`
when the value is an object; the `Outcome`'s `source` and `degraded` are
reported in the result `meta`. A `FrameworkError` (e.g. a `PermanentError`, or a
tripped breaker after retries) becomes a tool error (`isError=true`) with the
message, not a transport-level failure.
