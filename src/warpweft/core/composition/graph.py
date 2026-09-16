"""Dependency graph: validation before start, ordering for lifecycle.

Validated at build time, before anything starts:

- **missing dependencies** - a declared dependency is not among the configured
  components;
- **cycles** - the error names the cycle;
- **lifetime scope leak** - a process-lifetime component cannot depend on a
  scoped one: it would capture the first resolved instance and hand it to
  everyone. The error names the offending pair.

The graph also yields a startup order as layers (each layer can start in
parallel) and the reverse order for shutdown.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from warpweft.core.component import Lifetime
from warpweft.core.errors import ConfigurationError


@dataclass(frozen=True)
class GraphNode:
    """One component's place in the graph."""

    name: str
    dependencies: tuple[str, ...]
    lifetime: Lifetime


class DependencyGraph:
    """A validated dependency graph over the configured components."""

    def __init__(self, nodes: Mapping[str, GraphNode]) -> None:
        self._nodes = dict(nodes)
        self._check_missing()
        self._check_lifetime()
        self._check_cycles()

    def _check_missing(self) -> None:
        for node in self._nodes.values():
            for dep in node.dependencies:
                if dep not in self._nodes:
                    raise ConfigurationError(f"component '{node.name}' depends on '{dep}', which is not configured")

    def _check_lifetime(self) -> None:
        for node in self._nodes.values():
            if node.lifetime is not Lifetime.PROCESS:
                continue
            for dep in node.dependencies:
                if self._nodes[dep].lifetime is Lifetime.SCOPED:
                    raise ConfigurationError(
                        f"process component '{node.name}' cannot depend on scoped component '{dep}': "
                        f"it would capture a single scope's instance for all scopes"
                    )

    def _check_cycles(self) -> None:
        # DFS with colors; on a back edge, reconstruct the cycle for the message.
        WHITE, GREY, BLACK = 0, 1, 2
        color = dict.fromkeys(self._nodes, WHITE)
        stack: list[str] = []

        def visit(name: str) -> None:
            color[name] = GREY
            stack.append(name)
            for dep in self._nodes[name].dependencies:
                if color[dep] == GREY:
                    cycle = stack[stack.index(dep) :] + [dep]
                    raise ConfigurationError("dependency cycle: " + " -> ".join(cycle))
                if color[dep] == WHITE:
                    visit(dep)
            stack.pop()
            color[name] = BLACK

        for name in sorted(self._nodes):
            if color[name] == WHITE:
                visit(name)

    def startup_layers(self) -> list[tuple[str, ...]]:
        """Groups of components to start in order; each group can go in parallel.

        Dependencies land in earlier layers than their dependents.
        """
        indegree = {name: len(node.dependencies) for name, node in self._nodes.items()}
        dependents: dict[str, list[str]] = {name: [] for name in self._nodes}
        for name, node in self._nodes.items():
            for dep in node.dependencies:
                dependents[dep].append(name)

        layers: list[tuple[str, ...]] = []
        ready = sorted(name for name, deg in indegree.items() if deg == 0)
        while ready:
            layers.append(tuple(ready))
            nxt: list[str] = []
            for name in ready:
                for dependent in dependents[name]:
                    indegree[dependent] -= 1
                    if indegree[dependent] == 0:
                        nxt.append(dependent)
            ready = sorted(nxt)
        return layers

    def startup_order(self) -> tuple[str, ...]:
        """Flat startup order, dependencies first."""
        return tuple(name for layer in self.startup_layers() for name in layer)

    def shutdown_order(self) -> tuple[str, ...]:
        """Reverse of the startup order: dependents stop before dependencies."""
        return tuple(reversed(self.startup_order()))
