# CLAUDE.md

Agent operating manual for `work-timeline`. Rules, not a tour: the code is in `src/`, the reasons
in `docs/adr/`. Human setup and release steps: `CONTRIBUTING.md`.

## What this is

The contract for a shared work timeline (a closed vocabulary and three request models) and the
remote writer for it. The writer opens a unit when work starts and closes it when work ends
(ADR-0001), never raises (ADR-0002), and records a stopped unit as `cancelled` (ADR-0003). The
receiver validates with the same models the writer builds through (ADR-0004). The receiver is not
in this repository.

## Commands (CI runs exactly these, `.github/workflows/ci.yml`)

```bash
uv sync --all-groups                      # locked dev environment
uv run pytest -q                          # suite, including the README's Python block
uv run ruff check . && uv run ruff format --check .
uv run pre-commit run --all-files         # deployment-vocabulary and date hooks
uv run --group types mypy                 # --strict over src/
uv build                                  # wheel + sdist
```

## Code rules

- **The public API is the contract.** Paths, model fields, `vocab` values, the names in each
  module's `__all__`, and the CLI's arguments, defaults and exit codes. Changing any of them is a
  major version with a `CHANGELOG.md` entry naming what a consumer must change.
- **Never raise from a write.** A failed write is `False` / `None` plus one log line. A block's
  own exception is re-raised unchanged.
- **The API key is never logged and never accepted on argv.**
- **Docstrings state the contract** (Google style, `ruff` `D` rules): what it does, `Args`,
  `Returns`, `Raises` or "never raises", `Invariants`. No history, dates, or names of the systems
  that use the package: the pre-commit hook rejects deployment vocabulary. Full rules:
  `CONTRIBUTING.md` §Docstrings.
- **History has two homes:** what changed goes in `CHANGELOG.md` (under `Unreleased`); why goes in a
  new `docs/adr/NNNN-title.md` (MADR). A docstring keeps a one-line `Rationale: ADR-NNNN.` pointer.
- **Examples are technical and neutral:** CI jobs, builds, deploys, ETL runs, cron jobs, queue
  workers. Hosts are `*.example.com` or `*.test`.
- **Every `README.md` Python block runs** under `pytest-examples` (`tests/test_readme.py`). A
  fragment that cannot run is fenced `{.python test="skip"}`.
- Every module defines `__all__`; `tests/test_public_api.py` checks each name resolves.
- `mypy --strict` passes over `src/`; `py.typed` ships in the wheel.
- The only runtime dependency is pydantic. The default transport is stdlib `urllib`.

## Git and releases

- Branch + PR, never push `main`. Conventional Commits.
- Release = bump `version` and `__version__`, move `Unreleased` in `CHANGELOG.md`, merge, tag
  `vX.Y.Z` on `main`. `release.yml` attaches the wheel and sdist to a GitHub release. A published
  version is never replaced.
