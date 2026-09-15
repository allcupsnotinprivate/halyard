"""Write a component, derive its descriptor and settings JSON Schema.

The pipeline is not wired to the component here - this shows only the
contract: a component declares its own settings and marks entry points, and
``describe`` produces the identity, per-method IO schemas with effective
policies, and the combined config model (own fields + policy).

Run:
    uv run python examples/component_descriptor.py
"""

import json

from pydantic import BaseModel, Field, SecretStr

from halyard.core.component import AComponent, Criticality, Policy, describe, invocable


class SearchSettings(BaseModel):
    """The component's own settings - no policy fields here."""

    base_url: str
    api_key: SecretStr
    top_k: int = Field(default=10, ge=1)


class Document(BaseModel):
    id: str
    score: float


class SearchService(AComponent[SearchSettings, str, list[Document]]):
    name = "search"
    version = "1"
    dependencies = ("embedder",)
    criticality = Criticality.OPTIONAL

    @invocable
    async def query(self, text: str, limit: int = 10) -> list[Document]:
        """The main entry point - inherits the default policy chain."""
        return []

    # Health must never be retried or tripped by a breaker: pin a bare chain.
    @invocable(policy=Policy(chain=("timeout",)))
    async def probe(self) -> bool:
        return True


def main() -> None:
    descriptor = describe(SearchService)

    print(f"identity     : {descriptor.identity.uid}")
    print(f"criticality  : {descriptor.criticality}")
    print(f"dependencies : {descriptor.dependencies}")
    print("\ninvocables:")
    for name, spec in descriptor.invocables.items():
        inputs = list(spec.input_json_schema().get("properties", {}))
        print(f"  {name}: inputs={inputs} chain={spec.policy.chain}")

    print("\nsettings JSON Schema (own fields + policy):")
    print(json.dumps(descriptor.config_json_schema(), indent=2))


if __name__ == "__main__":
    main()
