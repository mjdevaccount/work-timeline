# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). Why a design is the way it is lives in
[`docs/adr/`](docs/adr/README.md).

## [Unreleased]

## [1.0.0] - 2026-11-03

### Changed

- **Breaking:** the default environment variables are `WORK_TIMELINE_BASE_URL` and
  `WORK_TIMELINE_API_KEY` (`client.BASE_URL_VAR`, `client.API_KEY_VAR`). They are read by
  `TimelineClient.from_env()` and by the CLI (`--base-url`'s fallback and `--key-var`'s default).
  To keep the previous names, pass `base_var=` / `key_var=` to `from_env()`, or `--key-var` to the
  CLI; both work on 0.2.0 too. A caller that passes `base_url` and `api_key` explicitly is
  unaffected.
- The package moved to the `src/` layout. The wheel's contents are unchanged.
- Every module defines `__all__`; docstrings state the contract in Google style.

### Added

- `CHANGELOG.md`, `CONTRIBUTING.md`, and `docs/adr/` with the six decisions the package was built
  on, recorded after the fact.
- CI: `ruff format --check`, ruff's docstring rules, a `pre-commit` hook that keeps deployment
  vocabulary out of the package, `mypy --strict`, a test matrix over Python 3.12 to 3.14 and
  Windows, a build check, and a test that runs the README's Python example.
- `renovate.json`, extending the shared ci-kit preset.

The wire contract (paths, models, field names, vocabulary) and the CLI's arguments and exit codes
are unchanged.

## [0.2.0] - 2026-10-23

### Added

- `python -m work_timeline record | open | close`: a CLI for writers that are not Python. It builds
  each body through the contract models, reads the API key from the environment variable
  `--key-var` names (never argv), prints the body with `--dry-run`, and reports the outcome as an
  exit code: 0 accepted, 2 bad input, 3 refused, 4 no response, 5 not configured. (ADR-0006)
- `TimelineClient(headers=...)`: extra request headers. The API key, `Content-Type` and `Accept`
  headers are set after them and cannot be replaced.

## [0.1.1] - 2026-10-23

### Fixed

- The wheel ships `py.typed`, so a consumer type-checking under `mypy --strict` can import the
  package.

## [0.1.0] - 2026-10-23

### Added

- `work_timeline.vocab`: the closed `KINDS`, `LAYERS` and `STATUSES`, `status_for()` (cancelled is
  not failed), `terminal()` (an unknown status becomes `failed`), `ERROR_MAX`.
- `work_timeline.contract`: `WorkOpen`, `WorkClose`, `WorkRecord` and their paths, shared by the
  receiver and every writer. (ADR-0004)
- `work_timeline.client.TimelineClient`: `open`, `close`, `record`, and `recorded()` /
  `arecorded()`, which open a unit on entry and close it on exit (ADR-0001), never raise
  (ADR-0002), and record a stopped unit as `cancelled` (ADR-0003).

[Unreleased]: https://github.com/mjdevaccount/work-timeline/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/mjdevaccount/work-timeline/compare/v0.2.0...v1.0.0
[0.2.0]: https://github.com/mjdevaccount/work-timeline/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/mjdevaccount/work-timeline/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/mjdevaccount/work-timeline/releases/tag/v0.1.0
