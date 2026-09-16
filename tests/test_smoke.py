"""Smoke: the package is importable and versioned."""

import pytest

import warpweft.core

pytestmark = pytest.mark.unit


def test_importable_and_versioned() -> None:
    assert warpweft.core.__version__ == "0.1.0"
