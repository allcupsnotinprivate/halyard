# Field formats

Field formats annotate a component's string inputs so their JSON Schema says
what shape the value is (an LLM tool or a config author sees the intent) and the
value is validated. A format is `Annotated` metadata - there is no registry, so
using and extending them is just types.

```python
from warpweft.formats import Ipv4, Uuid


class Lookup(AComponent[EmptySettings, str, dict]):
    @invocable
    async def locate(self, host: Ipv4, ticket: Uuid) -> Report: ...
```

The input schema then carries `{"type": "string", "format": "ipv4"}`, and a bad
value is rejected (at the MCP boundary, arguments are validated against the
input model before the call).

## Shipped formats

Only the standard JSON Schema string formats, with stdlib validators:
`Date`, `Time`, `DateTime`, `Email`, `Hostname`, `Ipv4`, `Ipv6`, `Uri`, `Uuid`,
`Regex`, `JsonPointer`.

## Custom formats

Define your own - a `Format` value plus an optional validator - and use it in
`Annotated`. No registration:

```python
from typing import Annotated
from warpweft.formats import Format


def _validate_sha256(value: str) -> None:
    if len(value) != 64 or not all(c in "0123456789abcdefABCDEF" for c in value):
        raise ValueError("expected a SHA-256 hex digest")


Sha256 = Annotated[str, Format("hash-sha256", "SHA-256 hex digest.", _validate_sha256)]
```

A `Format` without a validator only annotates the schema; with one, the value is
validated wherever the model is (component invocation via a tool, `warpweft
schema`, direct model use).
