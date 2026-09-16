"""Shared fixtures: both anyio backends, sample package, and an MCP client session."""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path
import sys

import anyio
from mcp import ClientSession
from mcp.shared.memory import create_client_server_memory_streams
import pytest

from halyard.mcp import build_server
from halyard.runtime import App

sys.path.insert(0, str(Path(__file__).parent))  # makes `sample_app` importable


@pytest.fixture(params=["asyncio", "trio"])
def anyio_backend(request: pytest.FixtureRequest) -> str:
    return str(request.param)


@pytest.fixture
def connect() -> Callable[[App], AbstractAsyncContextManager[ClientSession]]:
    """Return the ``connected(app)`` context manager for a test to use."""
    return connected


@asynccontextmanager
async def connected(app: App) -> AsyncIterator[ClientSession]:
    """Start the app, run its MCP server, yield a connected client session."""
    async with app.run(), create_client_server_memory_streams() as (client_streams, server_streams):
        server = build_server(app)
        server_read, server_write = server_streams
        client_read, client_write = client_streams

        async def run_server() -> None:
            await server.run(server_read, server_write, server.create_initialization_options(), raise_exceptions=True)

        async with anyio.create_task_group() as tg:
            tg.start_soon(run_server)
            async with ClientSession(client_read, client_write) as client:
                await client.initialize()
                yield client
            tg.cancel_scope.cancel()
