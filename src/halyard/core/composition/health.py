"""System health: liveness and readiness are different questions.

- **Liveness** asks only whether the process is up; it never touches
  dependencies. A live-but-not-ready process should not be restarted.
- **Readiness** asks whether the system can serve: every *required* component
  must be healthy. A degraded *optional* component does not break readiness but
  is reported in the detail.

Readiness aggregates bottom-up through the graph with criticality: a component
is downgraded when a *required* dependency is unhealthy, but an unhealthy
*optional* dependency leaves it alone (the dependent copes by degrading).
"""

from collections.abc import Mapping
from dataclasses import dataclass

from halyard.core.component import Criticality, HealthStatus


@dataclass(frozen=True)
class Readiness:
    """Aggregated readiness plus each component's effective status."""

    ready: bool
    components: Mapping[str, HealthStatus]


def aggregate_readiness(
    dependencies: Mapping[str, tuple[str, ...]],
    criticality: Mapping[str, Criticality],
    own: Mapping[str, HealthStatus],
) -> Readiness:
    """Combine each component's own health into a system readiness verdict.

    ``own`` is each component's self-reported health. A component's effective
    health is downgraded to unhealthy when one of its *required* dependencies
    is unhealthy. The system is ready when every required component is
    effectively healthy.
    """
    effective: dict[str, HealthStatus] = {}

    def resolve(name: str) -> HealthStatus:
        if name in effective:
            return effective[name]
        status = own[name]
        for dep in dependencies[name]:
            if criticality[dep] is Criticality.REQUIRED and status.is_ok and not resolve(dep).is_ok:
                status = HealthStatus.unhealthy(f"required dependency '{dep}' is not healthy")
        effective[name] = status
        return status

    reports = {name: resolve(name) for name in own}
    ready = all(reports[name].is_ok for name, crit in criticality.items() if crit is Criticality.REQUIRED)
    return Readiness(ready=ready, components=reports)
