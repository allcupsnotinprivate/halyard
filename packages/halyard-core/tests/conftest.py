"""Shared fixtures: every async test runs on both anyio backends."""

import pytest


@pytest.fixture(params=["asyncio", "trio"])
def anyio_backend(request: pytest.FixtureRequest) -> str:
    return str(request.param)
