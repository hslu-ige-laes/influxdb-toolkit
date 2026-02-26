# Contributing

## Setup

1. Use Python 3.10+.
2. Install dev dependencies:

```bash
pip install -e .[dev]
```

3. Run tests:

```bash
pytest
```

## Coding Rules

- Keep write/delete/admin paths safe by default (`allow_write=False`).
- Add tests for all behavior changes.
- Keep type hints and docstrings on public APIs.
- Avoid hardcoded credentials.

## Commit Style

Use conventional-style prefixes where possible:
- `feat:`
- `fix:`
- `docs:`
- `test:`
- `refactor:`

## Pull Requests

- Explain behavior change and rationale.
- Include test evidence.
- Update docs (`README.md`, `docs/*`) when behavior changes.

## Release Basics

- Bump version in `pyproject.toml`.
- Update `CHANGELOG.md`.
- Build and run `twine check` before publishing.
