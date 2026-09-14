# halyard

An asynchronous framework for building resilient tool and provider systems.

Repository - **uv-workspace** (monorepo): the root is not published and holds the shared
`uv.lock` and dev tooling, while the framework itself is distributed across
`halyard.*` namespace packages within `packages/`.

## What is inside

`halyard-core` (import namespace `halyard.core`) currently ships the two lowest layers:

- **Foundation** - error taxonomy with pluggable classification (`errors`),
  the `Clock` protocol with a manual test clock (`clock`), state-slicing axes
  instead of a hardcoded tenant concept (`axes`), the immutable
  `InvocationContext` with deadline math (`context`), `Outcome[T]` results
  (`outcome`) and uniform unit identity/lifecycle protocols (`unit`).
- **Pipeline** - the interceptor protocol and factories (`pipeline.interceptor`),
  a bounded LRU state store (`pipeline.state`), pure chain composition where
  the first link is the outermost (`pipeline.chain`), and two built-in links:
  per-attempt `timeout` and deadline-aware `retry` with full-jitter backoff
  (`pipeline.builtin`).

Async-only, built on [anyio](https://anyio.readthedocs.io/): the test suite runs
on both asyncio and trio.

## Requirements

- Python >= 3.11 (local dev pin: 3.14, see `.python-version`)
- [uv](https://docs.astral.sh/uv/)

## Structure

```
halyard/
├── pyproject.toml          # root: workspace + dev-deps, not published
├── uv.lock                 # one for the entire workspace
├── packages/
│   └── halyard-core/       # foundation + interceptor pipeline
├── examples/
│   └── retry_timeout.py    # runnable demo: timeout inside retry
└── docs/
```

All packages share the import namespace `halyard.<subpackage>` (PEP 420);
`halyard-core` provides `halyard.core`, a future `halyard-<name>` provides
`halyard.<name>`. Internal dependencies are resolved from the workspace
(`tool.uv.sources`).

## Quick start

```bash
uv sync --all-packages          # shared venv with all packages (editable)
uv run pre-commit install       # git hooks

uv run python examples/retry_timeout.py   # see the pipeline in action

uv run pytest                   # tests across all packages/*/tests
uv run ruff check .             # linter
uv run ruff format --check .    # formatter
uv run --all-packages mypy $(find packages -maxdepth 3 -name src -type d)  # type checking
```

## A taste of the API

```python
from halyard.core.axes import AxisRegistry
from halyard.core.clock import SystemClock
from halyard.core.context import InvocationContext
from halyard.core.pipeline.builtin.retry import RetryFactory, RetrySettings
from halyard.core.pipeline.builtin.timeout import TimeoutFactory, TimeoutSettings
from halyard.core.pipeline.chain import build_chain
from halyard.core.pipeline.state import InMemoryStateStore

clock = SystemClock()
chain = build_chain(
    [  # first link is the outermost one
        RetryFactory(RetrySettings(attempts=5, base_delay=0.1, max_delay=2.0), clock),
        TimeoutFactory(TimeoutSettings(seconds=1.0), clock),
    ],
    InMemoryStateStore(),
    AxisRegistry(),
    my_async_call,  # async (ctx) -> Outcome
)

outcome = await chain(InvocationContext(operation="fetch", correlation_id="c-1"))
```

## Adding a workspace package

Create `packages/halyard-<name>/` with a `pyproject.toml` and
`src/halyard/<name>/`; it is picked up automatically via the `packages/*`
member pattern. Append its `src` to `mypy_path` in the root `pyproject.toml`.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) - commit format, DCO, how to run checks.
