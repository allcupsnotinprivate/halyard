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
override, a `description` (else the method docstring is used), the MCP
annotation hints `read_only`, `destructive`, `idempotent`, `open_world`, and
free-form `tags` used to [filter](#filtering) which tools a server exposes. A
`@tool` on a method that is not `@invocable` is rejected when the server is
built.

An [action](actions.md) is marked automatically - its `execute` is a tool by
default (opt out with `entrypoint = False`), from class-level metadata - so you
rarely write `@tool` yourself.

## Serving

```python
from warpweft.mcp import run_stdio

anyio.run(run_stdio, app)  # local host (Claude Desktop, an IDE)
```

`run_stdio` starts the app, serves its tools over stdio, and stops the app when
the stream closes. For programmatic use (or a future HTTP transport),
`build_server(app)` returns a transport-agnostic MCP server.

## Filtering

One app can back several servers with different tool sets - a read-only server
for an assistant, the full set for an operator console. `collect_tools`,
`build_server` and `run_stdio` take three narrowing arguments, applied in
order:

```python
build_server(app, tags={"public"})  # any-match on @tool tags
build_server(app, include={"search__*"})  # only these names (fnmatch globs)
build_server(app, exclude={"billing__refund"})  # drop these names; wins over include
```

A tool with no tags never passes a `tags` filter, so tagging works as a
whitelist: a forgotten tag keeps a tool private rather than exposing it. The
filter is validated strictly - a tag no tool declares, a pattern that matches
no tool, or a filter that leaves nothing to expose raises a `FrameworkError`
instead of quietly serving the wrong set.

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
reported in the result `meta`.

## Errors

Any failure - framework or user code - becomes a tool error (`isError=true`),
never a transport-level failure. The error tells the model what to do next: a
one-sentence hint is appended to the message, and the result `meta` carries
machine-readable guidance:

| meta key | Meaning |
| --- | --- |
| `warpweft.error` | a stable code: `invalid_arguments`, `circuit_open`, `timeout`, `retry_exhausted`, `unavailable`, `transient`, `permanent`, `error` |
| `warpweft.retryable` | whether calling again can help |
| `warpweft.retry_after_s` | for `circuit_open`: seconds until the breaker admits a probe |
| `warpweft.attempts` | for `retry_exhausted`: attempts already spent |

The codes mirror the [error taxonomy](composition.md): transient failures
(timeouts, an open breaker, a degraded component) are retryable, permanent
ones are not, and an unclassified exception is reported as non-retryable
`error` - the same stance the retry link takes.

## Progress and cancellation

A long-running invocable reports progress without knowing what transport
drives it:

```python
from warpweft import report_progress


class Indexer(AComponent[IndexerSettings, str, Report]):
    @tool(description="Rebuild the search index.")
    @invocable
    async def rebuild(self) -> Report:
        for step, shard in enumerate(self._shards, start=1):
            await self._index(shard)
            await report_progress(step, total=len(self._shards), message=shard)
        ...
```

`report_progress` is a no-op unless the transport installed a sink
(`warpweft.core.context.use_progress_sink`). The MCP server installs one per
call, so reports become `notifications/progress` exactly when the client sent
a `progressToken`. Reports are fire-and-forget - a failed notification never
fails the call.

Cancellation needs no code at all: when the client cancels an MCP request,
the SDK cancels the handler's anyio scope, the cancellation unwinds the
policy chain, and the component's cleanup (`finally` blocks, context
managers) runs as usual.
