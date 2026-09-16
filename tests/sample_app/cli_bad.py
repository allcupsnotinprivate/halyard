"""An App whose config fails validation, for CLI `check` error tests.

Uses its own Registry for isolation from the process-wide default one.
"""

from pydantic import BaseModel

from warpweft.core.component import AComponent, invocable
from warpweft.core.composition import Registry
from warpweft.runtime import App


class NeedsUrl(BaseModel):
    url: str  # required, never provided -> build() fails


class CliBad(AComponent[NeedsUrl, str, str]):
    name = "cli-bad"

    @invocable
    async def go(self) -> str:
        return "x"


_registry = Registry()
_registry.register(CliBad)

app = App(registry=_registry)
