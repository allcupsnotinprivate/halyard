"""Health reporting for components.

A component answers ``health()`` with a :class:`HealthStatus`. The three
states are enough for aggregation: a healthy component, one that is up but
degraded (serving stubs / partial data), and one that is down. Readiness vs
liveness aggregation over the dependency graph is built on top of this later.
"""

from dataclasses import dataclass
from enum import StrEnum


class Health(StrEnum):
    """Coarse health verdict of a single component."""

    OK = "ok"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass(frozen=True, slots=True)
class HealthStatus:
    """A health verdict plus an optional human-readable detail."""

    state: Health
    detail: str | None = None

    @classmethod
    def ok(cls, detail: str | None = None) -> "HealthStatus":
        return cls(Health.OK, detail)

    @classmethod
    def degraded(cls, detail: str | None = None) -> "HealthStatus":
        return cls(Health.DEGRADED, detail)

    @classmethod
    def unhealthy(cls, detail: str | None = None) -> "HealthStatus":
        return cls(Health.UNHEALTHY, detail)

    @property
    def is_ok(self) -> bool:
        return self.state is Health.OK
