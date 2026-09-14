"""InvocationContext: deadlines on ManualClock, child immutability, contextvar."""

import pytest

from halyard.core.clock import ManualClock
from halyard.core.context import InvocationContext, current_context, use_context

pytestmark = pytest.mark.unit


def ctx(**overrides: object) -> InvocationContext:
    defaults: dict[str, object] = {"operation": "op", "correlation_id": "cid"}
    defaults.update(overrides)
    return InvocationContext(**defaults)  # type: ignore[arg-type]


def test_remaining_without_deadline_is_none() -> None:
    clock = ManualClock()
    assert ctx().remaining(clock) is None
    assert not ctx().expired(clock)


def test_remaining_counts_down_on_manual_clock() -> None:
    clock = ManualClock()
    c = ctx(deadline=10.0)
    assert c.remaining(clock) == 10.0
    clock.advance(4)
    assert c.remaining(clock) == 6.0
    assert not c.expired(clock)


def test_expired_deadline_detected_and_remaining_never_negative() -> None:
    clock = ManualClock()
    c = ctx(deadline=5.0)
    clock.advance(7)
    assert c.expired(clock)
    assert c.remaining(clock) == 0.0


def test_deadline_boundary_is_expired() -> None:
    clock = ManualClock()
    c = ctx(deadline=5.0)
    clock.advance(5)
    assert c.expired(clock)


def test_child_does_not_mutate_parent() -> None:
    parent = ctx(attempt=1, deadline=5.0)
    child = parent.child(attempt=2)
    assert parent.attempt == 1
    assert child.attempt == 2
    assert child.deadline == parent.deadline
    assert child.operation == parent.operation


def test_context_is_immutable() -> None:
    with pytest.raises(AttributeError):
        ctx().attempt = 5  # type: ignore[misc]


def test_bag_is_shared_between_parent_and_child() -> None:
    """The bag is the exchange channel between links, not per-attempt state."""
    parent = ctx()
    child = parent.child(attempt=2)
    child.bag["seen"] = True
    assert parent.bag["seen"] is True


def test_bag_can_be_isolated_explicitly() -> None:
    parent = ctx()
    parent.bag["k"] = "v"
    child = parent.child(bag={})
    child.bag["k"] = "other"
    assert parent.bag["k"] == "v"


def test_current_context_helpers() -> None:
    assert current_context() is None
    c = ctx()
    with use_context(c) as installed:
        assert installed is c
        assert current_context() is c
        inner = c.child(attempt=2)
        with use_context(inner):
            assert current_context() is inner
        assert current_context() is c
    assert current_context() is None
