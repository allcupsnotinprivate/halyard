"""Runnable demo: expose a component's @tool invocables over MCP.

A component marks one method with @tool; the app serves it as an MCP tool. To
keep the example self-contained it drives an in-memory MCP client against the
server (a real host would connect over stdio via ``run_stdio(app)``).

Run:
    uv run python examples/mcp_tools.py
"""

import anyio
from mcp import ClientSession
from mcp.shared.memory import create_client_server_memory_streams
from pydantic import BaseModel

from halyard import AComponent, App, EmptySettings, Registry, invocable
from halyard.mcp import build_server, tool


class Forecast(BaseModel):
    city: str
    summary: str
    high_c: int


class Weather(AComponent[EmptySettings, str, Forecast]):
    name = "weather"

    @tool(description="Get today's forecast for a city.", read_only=True)
    @invocable
    async def forecast(self, city: str) -> Forecast:
        return Forecast(city=city, summary="sunny", high_c=21)

    @invocable
    async def _refresh(self) -> None:  # not a @tool -> never exposed
        return None


async def main() -> None:
    registry = Registry()
    registry.register(Weather)
    app = App(registry=registry)

    async with app.run(), create_client_server_memory_streams() as (client_streams, server_streams):
        server = build_server(app)
        async with anyio.create_task_group() as tg:
            tg.start_soon(
                lambda: server.run(*server_streams, server.create_initialization_options(), raise_exceptions=True)
            )
            async with ClientSession(*client_streams) as client:
                await client.initialize()

                tools = await client.list_tools()
                for t in tools.tools:
                    print(f"tool: {t.name} - {t.description}")
                    print(f"  input : {list(t.input_schema['properties'])}")
                    print(f"  output: {t.output_schema['type'] if t.output_schema else None}")
                    print(f"  read_only: {t.annotations.read_only_hint if t.annotations else None}")

                result = await client.call_tool("weather__forecast", {"city": "Oslo"})
                print("\ncall weather__forecast(city='Oslo'):")
                print(f"  structured: {result.structured_content}")
                print(f"  meta      : {result.meta}")
            tg.cancel_scope.cancel()


if __name__ == "__main__":
    anyio.run(main)
