"""Runnable demo: register components, build a container, invoke through it.

A ``search`` component depends on an ``embedder``. Both are registered, then a
container is built from a small config that turns on retry + timeout for the
search method. Starting the container brings them up in dependency order;
``invoke`` runs the method through its policy chain; readiness aggregates their
health; stopping tears down in reverse.

Run:
    uv run python examples/composition_container.py
"""

import anyio
from pydantic import BaseModel

from halyard.core.component import AComponent, EmptySettings, invocable
from halyard.core.composition import Container, Registry
from halyard.core.errors import TransientError

registry = Registry()


@registry.register
class Embedder(AComponent[EmptySettings, str, list[float]]):
    name = "embedder"

    @invocable
    async def embed(self, text: str) -> list[float]:
        return [float(len(text)), 1.0, 2.0]


class SearchSettings(BaseModel):
    index: str


@registry.register
class Search(AComponent[SearchSettings, str, list[str]]):
    name = "search"
    dependencies = ("embedder",)

    def __init__(self, settings: SearchSettings) -> None:
        super().__init__(settings)
        self._attempts = 0

    def endpoint(self) -> str | None:
        return self.settings.index  # link state is sliced per index host

    @invocable
    async def query(self, text: str) -> list[str]:
        # The first attempt fails transiently; retry recovers it.
        self._attempts += 1
        if self._attempts == 1:
            raise TransientError("index warming up")
        embedder: Embedder = self.dependency("embedder")  # type: ignore[assignment]
        vector = await embedder.embed(text)
        return [f"hit for {text!r} near {vector}"]


async def main() -> None:
    config = {
        "embedder": {},
        "search": {
            "index": "primary",
            "policy": {
                "retry": {"attempts": 3, "base_delay": 0.0, "max_delay": 0.1},
                "timeout": {"seconds": 2.0},
            },
        },
    }
    container = Container.build(registry, config)
    await container.start()
    print(f"liveness : {(await container.liveness()).state}")
    print(f"readiness: ready={(await container.readiness()).ready}")

    outcome = await container.invoke("search", "query", text="halyard")
    print("\ninvoke search.query('halyard'):")
    print(f"  value    = {outcome.value}")
    print(f"  attempts = {outcome.attempts} (first attempt failed, retry recovered)")
    print(f"  source   = {outcome.source}")

    explanation = container.explain("search", "query")
    print("\nexplain search.query:")
    print(f"  chain      = {explanation.chain}")
    print(f"  provenance = {dict(explanation.provenance)}")
    print(f"  breakers   = {container.snapshot().breakers}")

    await container.stop()
    print("\nstopped")


if __name__ == "__main__":
    anyio.run(main)
