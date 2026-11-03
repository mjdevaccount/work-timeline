# Contributing

## Setup

```
uv sync --all-groups         # the locked dev environment
uv run pre-commit install    # the vocabulary hook, on every commit
uv run pytest -q             # the suite, including the README's Python example
uv run ruff check . && uv run ruff format --check .
uv run --group types mypy    # --strict over src/
```

CI (`.github/workflows/ci.yml`) runs the same commands on Python 3.12 to 3.14 and on Windows,
builds the wheel and sdist, scans the history for secrets, and fails a new duplicated block of
code.

## Docstrings

A docstring states the contract. Its reader is someone calling the function, not someone auditing
why it was written.

1. **Contract only.** What it does, `Args:`, `Returns:`, `Raises:` (or that it never raises), in
   the present tense, Google style. Rules that always hold go in an `Invariants:` section.
2. **No history and no deployment detail.** No incident dates, ticket ids, or names of the
   systems, hosts or services that use the package. The *reason* for a design choice moves to an
   ADR, and the docstring keeps a one-line pointer (`Rationale: ADR-0002.`).
3. **Emphasis by structure, not capitals.** An invariant goes in `Invariants:`; a warning goes in
   its own sentence. Capitals are for constants and acronyms.
4. **Neutral examples.** CI jobs, builds, deploys, ETL runs, cron jobs, queue workers.

`ruff` enforces the Google layout (`D` rules). A `pre-commit` hook (`.pre-commit-config.yaml`)
rejects deployment vocabulary in `src/`, `tests/`, `docs/` and the top-level Markdown, and dates
in `src/`.

## Where history goes

- **What changed**: `CHANGELOG.md` ([Keep a Changelog](https://keepachangelog.com/en/1.1.0/)),
  under `Unreleased` until a release.
- **Why, with the evidence**: `docs/adr/NNNN-title.md` ([MADR](https://adr.github.io/madr/)).
  Evidence is stated without naming the system it came from ("a finished-unit model without an
  `error` field dropped the key on every failure row and answered 200").

## Compatibility

The wire contract (paths, model fields, vocabulary), the public names in each module's `__all__`,
and the CLI's arguments and exit codes are the public API. Changing one is a major version. A new
kind, layer or status is a minor version, released to the receiver before any writer uses it
(ADR-0005).

## Releasing

Bump `version` in `pyproject.toml` and `__version__` in `src/work_timeline/__init__.py` (a test
checks they agree), move `Unreleased` in `CHANGELOG.md` under the new version, and merge. Then push
a `vX.Y.Z` tag on `main`. `release.yml` checks the tag against the version, runs the suite, builds,
and attaches the wheel and sdist to a GitHub release. Consumers pin the wheel URL, so a published
file is never replaced; a fix is a new version.
