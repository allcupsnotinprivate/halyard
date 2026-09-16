"""A component discovered by walking the package."""

from warpweft.core.component import AComponent, EmptySettings, invocable
from warpweft.runtime import component


@component
class SampleWidget(AComponent[EmptySettings, None, str]):
    @invocable
    async def ping(self) -> str:
        return "widget-pong"
