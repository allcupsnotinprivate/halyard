"""An App wired for the CLI tests (loaded by 'module:attribute').

Uses its own Registry so it is isolated from the process-wide default one
(other fixtures register there).
"""

from pydantic import BaseModel, SecretStr

from warpweft.core.axes import ScopeSpec
from warpweft.core.component import AComponent, Criticality, EmptySettings, Lifetime, invocable
from warpweft.core.composition import Registry
from warpweft.runtime import App


class ApiSettings(BaseModel):
    base_url: str = "https://api.example.com"
    api_key: SecretStr = SecretStr("topsecret")


class CliApi(AComponent[ApiSettings, str, dict]):
    name = "cli-api"
    criticality = Criticality.OPTIONAL

    @invocable
    async def fetch(self, path: str) -> dict:
        return {}


class CliReports(AComponent[EmptySettings, None, str]):
    """Scoped, with a dependency and no configured policy - exercises the
    scope/dependencies/empty-provenance output paths."""

    name = "cli-reports"
    lifetime = Lifetime.SCOPED
    scope = ScopeSpec(("tenant",))
    dependencies = ("cli-api",)

    @invocable
    async def daily(self) -> str:
        return "report"


_registry = Registry()
_registry.register(CliApi)
_registry.register(CliReports)

app = App(
    registry=_registry,
    config={"cli-api": {"policy": {"retry": {"attempts": 3, "base_delay": 0.1, "max_delay": 1.0}}}},
)

not_an_app = object()
