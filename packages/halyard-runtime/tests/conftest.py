"""Shared fixtures: both anyio backends, and the sample package on sys.path."""

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent))  # makes `sample_app` importable


@pytest.fixture(params=["asyncio", "trio"])
def anyio_backend(request: pytest.FixtureRequest) -> str:
    return str(request.param)
