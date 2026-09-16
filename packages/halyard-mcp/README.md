# halyard-mcp

Expose a halyard component's invocables as [Model Context
Protocol](https://modelcontextprotocol.io) tools. Mark a method with `@tool`
(on top of `@invocable`) and it becomes an LLM-callable tool; every call runs
through the full pipeline (retry, cache, breaker, telemetry) via the container.

```python
from halyard.core.component import AComponent, invocable
from halyard.mcp import tool


class Weather(AComponent[WeatherSettings, str, Forecast]):
    @tool(description="Get the forecast for a city.")
    @invocable
    async def forecast(self, city: str) -> Forecast: ...
```

```python
from halyard.mcp import run_stdio

anyio.run(run_stdio, app)  # serve the app's tools over stdio
```

Only `@tool`-marked invocables are exposed; everything else stays private.
`@tool` lives here, not in the core, so the core never learns about MCP.
