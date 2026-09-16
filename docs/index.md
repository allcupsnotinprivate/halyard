<img class="ww-logo" src="assets/logo-rounded.png" alt="Warpweft logo">

# Warpweft

A declarative framework for building **resilient, observable service
components** in async Python. You write a component's *calls*; warpweft wraps
every call with retry, timeout, circuit breaking, caching, concurrency limiting
and telemetry - driven by configuration, not boilerplate.

Async-only, built on [anyio](https://anyio.readthedocs.io/) (asyncio and trio).
Typed throughout (`mypy --strict`).

## Install

```bash
pip install warpweft          # core + runtime
pip install warpweft[mcp]     # + expose components as Model Context Protocol tools
pip install warpweft[yaml]    # + YAML config files
```

## A taste

```python
from warpweft import AComponent, App, component, invocable


@component
class Weather(AComponent[WeatherSettings, str, dict]):
    @invocable
    async def forecast(self, city: str) -> dict:
        resp = await self._client.get(f"/forecast/{city}")
        resp.raise_for_status()
        return resp.json()


app = App(
    env_prefix="MYAPP",
    config={"weather": {"policy": {"retry": {"attempts": 3, "base_delay": 0.1, "max_delay": 1.0}}}},
)

async with app.run():
    forecast = await app.proxy(Weather).forecast(city="oslo")  # runs through the chain
```

## Where to go next

- **[Write your first component](first-component.md)** - from nothing to a tested component.
- **Guides** - [Runtime](runtime.md), [Composition](composition.md),
  [Field formats](formats.md), [Telemetry](telemetry.md), [Logging](logging.md),
  [MCP tools](mcp.md).
- **[API reference](reference/warpweft/index.md)** - generated from the source.

Everything useful is importable from `warpweft`; focused surfaces have their own
module - `warpweft.formats`, `warpweft.testing`, and `warpweft.mcp` (with the
extra). The internal layers remain available as `warpweft.core.*` and
`warpweft.runtime.*`.
