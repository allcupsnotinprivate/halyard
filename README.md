<p align="center">
  <img src="docs/assets/logo-rounded.png" alt="warpweft" width="180">
</p>

# warpweft

A declarative framework for building resilient, observable service components in
async Python. You write a component's *calls*; warpweft wraps every call with
retry, timeout, circuit breaking, caching, concurrency limiting and telemetry -
driven by configuration, not boilerplate.

Async-only, built on [anyio](https://anyio.readthedocs.io/) (runs on asyncio and
trio). Typed throughout (`mypy --strict`).

## Install

```bash
pip install warpweft          # core + runtime
pip install warpweft[mcp]     # + expose components as Model Context Protocol tools
pip install warpweft[yaml]    # + YAML config files
```

## A taste

```python
from warpweft import AComponent, App, component, invocable


class WeatherSettings(BaseModel):
    base_url: str


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

Everything useful is importable from `warpweft`; focused surfaces have their own
module - `warpweft.formats` (field formats), `warpweft.testing` (test helpers),
`warpweft.mcp` (MCP tools, with the extra). The internal layers remain available
as `warpweft.core.*` and `warpweft.runtime.*`.

## Documentation

- [Write your first component](docs/first-component.md) - from nothing to a tested component.
- [Runtime](docs/runtime.md) - the App, `@component`, autodiscovery, config and the lifespan.
- [Composition](docs/composition.md) - registry, container, dependency graph, lifecycle, axes, health.
- [Telemetry](docs/telemetry.md) - spans, metrics and the semantic conventions.
- [Logging](docs/logging.md) - the library logging convention.
- [MCP tools](docs/mcp.md) - exposing invocables to LLMs.

## Requirements

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/) for development

## Development

```bash
uv sync                         # dev environment (editable install + tools)
uv run pre-commit install       # git hooks

uv run pytest                   # tests, on both anyio backends
uv run ruff check .             # linter
uv run ruff format --check .    # formatter
uv run mypy src                 # type checking
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the commit format, DCO and checks.
