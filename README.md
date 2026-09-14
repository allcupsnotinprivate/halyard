# halyard

An asynchronous framework for building system tools and providers.

Repository — **uv-workspace** (monorepo): the root is not published and holds the shared
`uv.lock` and dev tooling, while the framework itself is distributed across
`halyard.*` namespace packages within `packages/`.

## Структура

```
halyard/
├── pyproject.toml          # root: workspace + dev-deps
├── uv.lock                 # one for entire workspace
├── packages/
│   └── halyard-core/       # Core: DI, actions/providers, tenancy, observability
├── examples/
└── docs/
```

All packages use the shared import namespace `halyard.<subpackage>` (PEP 420);
thus, `halyard-core` provides `halyard.core`, `halyard-<example>` provides `halyard.<example>`,
and so on. Internal dependencies are resolved from the workspace (`tool.uv.sources`).

## Требования

- Python 3.14 (see `.python-version`)
- [uv](https://docs.astral.sh/uv/)

## Quick Start

```bash
uv sync --all-packages          # shared venv with all packages (editable)
uv run pre-commit install       # git hooks

uv run pytest                   # tests across all packages/*/tests
uv run ruff check . # linter
uv run ruff format --check . # formatter
uv run --all-packages mypy $(find packages -maxdepth 3 -name src -type d)  # type checking
```

New package: create `packages/halyard-<name>/` with `pyproject.toml` and
`src/halyard/<name>/`; it will be automatically included in the workspace via the `packages/*` pattern.

## Вклад

См. [CONTRIBUTING.md](CONTRIBUTING.md) - формат коммитов, DCO, запуск проверок.
