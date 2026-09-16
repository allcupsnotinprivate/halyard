# warpweft

<p align="center">
  <em>A declarative framework for resilient, observable service components in async Python.</em>
</p>

<p align="center">
  <a href="https://pypi.org/project/warpweft/"><img src="https://img.shields.io/pypi/v/warpweft.svg" alt="PyPI version"></a>
  <a href="https://pypi.org/project/warpweft/"><img src="https://img.shields.io/pypi/pyversions/warpweft.svg" alt="Supported Python versions"></a>
  <a href="https://github.com/allcupsnotinprivate/warpweft/actions/workflows/ci.yml"><img src="https://github.com/allcupsnotinprivate/warpweft/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://allcupsnotinprivate.github.io/warpweft/"><img src="https://img.shields.io/badge/docs-online-4c9aff.svg" alt="Documentation"></a>
  <a href="https://opensource.org/license/apache-2-0"><img src="https://img.shields.io/badge/license-Apache--2.0-blue.svg" alt="License: Apache-2.0"></a>
</p>

You write a component's *calls*; warpweft wraps every call with retry, timeout,
circuit breaking, caching, concurrency limiting and telemetry - driven by
configuration, not boilerplate. Async-only, built on
[anyio](https://anyio.readthedocs.io/) (runs on asyncio and trio) and typed
throughout (`mypy --strict`).

## Features

- **Resilience, declared** - retry, timeout, circuit breaker, caching,
  concurrency limiting and graceful degradation wrap every call, driven by config.
- **Observable by default** - OpenTelemetry spans and metrics with consistent
  semantic conventions.
- **Composition** - a component registry, dependency-injection container,
  dependency graph, lifecycle and health checks.
- **Config-driven** - policies from environment, TOML or YAML; no per-call
  boilerplate.
- **LLM-ready** - expose invocables as Model Context Protocol tools.
- **Async & typed** - built on anyio (asyncio and trio), `mypy --strict` throughout.

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

Full documentation - getting started, guides and the auto-generated API
reference - lives at **https://allcupsnotinprivate.github.io/warpweft/**.

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

See `CONTRIBUTING.md` in the repository for the commit format, DCO and checks.
