# halyard-runtime

The application layer over `halyard-core`: an `App` facade that owns the
registry and container lifecycle, a `@component` decorator, package
autodiscovery, and environment-based configuration.

```python
from halyard.runtime import App, component


@component
class Profiles(AComponent[ProfilesSettings, str, dict]): ...


app = App(env_prefix="MYAPP")
app.autodiscover("myapp.components")

async with app.run() as container:
    data = await container.proxy(Profiles).get(user_id="42")
```
