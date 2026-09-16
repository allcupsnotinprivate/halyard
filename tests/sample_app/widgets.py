"""A component discovered by walking the package."""

from halyard.core.component import AComponent, EmptySettings, invocable
from halyard.runtime import component


@component
class SampleWidget(AComponent[EmptySettings, None, str]):
    @invocable
    async def ping(self) -> str:
        return "widget-pong"
