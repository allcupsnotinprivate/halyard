# How to Contribute

Thanks for your interest in the project! Here is the essential information you need before submitting a PR

## Branches and PRs

- Do not push directly to `main`—work in a separate branch and open a Pull Request
- Keep PRs small and focused on a single task

## Commit Format

Conventional Commits, messages in English:

```
<type>(<scope>): <short description>
```

Allowed `type` values: `feat`, `fix`, `refactor`, `test`, `chore`, `ci`.

Examples:

```
feat(pipelines): add retry policy to step runner
fix(http): handle scorer timeout
```