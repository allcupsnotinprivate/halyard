"""Smoke: the package is importable and versioned."""

import re

import pytest

import warpweft.core

pytestmark = pytest.mark.unit


def test_importable_and_versioned() -> None:
    # Assert it is versioned, not a specific value, so a release bump is enough.
    assert re.fullmatch(r"\d+\.\d+\.\d+.*", warpweft.core.__version__)
