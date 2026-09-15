"""Runnable demo of halyard-runtime: @component + App + env config.

A component registers itself with the module-level decorator; the App merges
programmatic config with environment variables (env wins per field), starts
the container, and serves typed calls through a proxy.

Run:
    uv run python examples/runtime_app.py
"""

import os

import anyio
from pydantic import BaseModel

from halyard.core.component import AComponent, invocable
from halyard.core.errors import TransientError
from halyard.runtime import App, component


class WeatherSettings(BaseModel):
    city_default: str = "amsterdam"


@component  # registered under the derived name "weather"
class Weather(AComponent[WeatherSettings, str, str]):
    def __init__(self, settings: WeatherSettings) -> None:
        super().__init__(settings)
        self._attempts = 0

    @invocable
    async def forecast(self, city: str = "") -> str:
        self._attempts += 1
        if self._attempts == 1:
            raise TransientError("satellite warming up")  # retry recovers this
        return f"sunny in {city or self.settings.city_default}"


async def main() -> None:
    # Simulate deployment env (a real app just reads os.environ / a .env file):
    os.environ["DEMO_WEATHER__CITY_DEFAULT"] = "reykjavik"
    app = App(
        config={"weather": {"policy": {"retry": {"attempts": 3, "base_delay": 0.05, "max_delay": 0.5}}}},
        env_prefix="DEMO",
    )

    async with app.run():
        weather = app.proxy(Weather)  # typed facade through the full chain
        print(f"forecast()        = {await weather.forecast()!r}   (env set the default city)")
        print(f"forecast('oslo')  = {await weather.forecast(city='oslo')!r}")

        explanation = app.container.explain("weather", "forecast")
        print(f"\nchain = {explanation.chain}")
        print(f"settings = {app.container.resolved_settings('weather')}")

    print("\nstopped")


if __name__ == "__main__":
    anyio.run(main)
