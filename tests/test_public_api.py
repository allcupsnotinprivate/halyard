"""The public import surface: everything useful is reachable from `halyard`."""

import pytest

pytestmark = pytest.mark.unit


def test_top_level_reexports_core_and_runtime() -> None:
    import halyard

    for name in ("App", "AComponent", "invocable", "component", "Container", "Registry", "Outcome"):
        assert hasattr(halyard, name), name
    assert halyard.__version__
    # everything advertised in __all__ actually resolves
    for name in halyard.__all__:
        assert hasattr(halyard, name), name


def test_formats_module_reexports_core_formats() -> None:
    from halyard import formats

    assert formats.Ipv4 is not None
    assert formats.Format is not None
    for name in formats.__all__:
        assert hasattr(formats, name), name


def test_testing_module_reexports_core_testing() -> None:
    from halyard import testing

    assert testing.drive is not None
    assert testing.ManualClock is not None
    for name in testing.__all__:
        assert hasattr(testing, name), name


def test_mcp_is_reachable_with_the_extra() -> None:
    from halyard.mcp import build_server, tool

    assert build_server is not None
    assert tool is not None
