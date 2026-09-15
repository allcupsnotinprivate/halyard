# Runtime (halyard-runtime)

The application layer over the core: one `App` object owns the registry, the
configuration and the container lifecycle. The core stays explicit and
instance-scoped; the runtime adds the convenient defaults an application wants.

## Declaring components

```python
from halyard.runtime import App, component


@component  # module-level: registers into the default registry
class Weather(AComponent[WeatherSettings, str, str]):
    @invocable
    async def forecast(self, city: str) -> str: ...
```

The module-level `@component` writes to a process-wide **default registry**
(the convenient path, like Celery's `shared_task`). For full isolation -
several independent apps in one process, hermetic tests - give the app its own
registry and use `@app.component`:

```python
app = App(registry=Registry())


@app.component
class Weather(...): ...
```

## Autodiscovery

Registration stays explicit; discovery only removes the manual import list:

```python
app.autodiscover("myapp.components")  # imports the package's modules
```

Modules with a leading underscore are skipped. There is deliberately no
metaclass auto-registration: subclassing is not intent to register.

## Configuration

`App` merges two layers into the deployment config (field by field, env wins):

```python
app = App(
    env_prefix="MYAPP",
    config={"weather": {"policy": {"retry": {...}}}},
)
```

Environment convention: `<PREFIX>_<COMPONENT>__<FIELD>[__<NESTED>...]`:

```
MYAPP_WEATHER__CITY_DEFAULT=reykjavik
MYAPP_WEATHER__POLICY__RETRY__ATTEMPTS=3
```

Values parse as JSON when possible (numbers, booleans, lists, objects), else
stay strings - the core's validation coerces and reports errors with the field
path and source. Prefixed variables without `__` (e.g. `MYAPP_DEBUG`) are the
application's own and are ignored; a `__`-shaped variable naming an unknown
component is an error (almost always a typo). Every registered component is
included in the container - an absent config section means "all defaults".

All `Container.build` options (classifier, axes, telemetry providers,
`framework_defaults`, a `SettingsResolver`, timeouts) pass through `App(...)`.

## Lifecycle

```python
async with app.run() as container:
    outcome = await app.invoke("weather", "forecast", city="oslo")
    weather = app.proxy(Weather)  # typed facade through the chain
    raw = await app.get(Weather)  # raw instance - bypasses the chain!
```

### Embedding into a host

`app.lifespan` is a framework-agnostic lifespan: start on enter, stop (with
the drain) on exit. It accepts and ignores whatever the host passes, so the
bound method plugs into anything that takes a lifespan callable:

```python
app = App(env_prefix="MYAPP")
app.autodiscover("myapp.components")

api = FastAPI(lifespan=app.lifespan)  # or Starlette(lifespan=app.lifespan)
```

Nothing is published into the host - handlers reach the running system through
the `app` object they already have (`app.proxy(...)`, `app.invoke(...)`,
`app.container`). For hosts with startup/shutdown callback pairs instead of a
lifespan (e.g. aiohttp), call `await app.start()` / `await app.stop()` from
those callbacks; standalone scripts can simply do `async with app.lifespan():`
or `async with app.run() as container:`.
