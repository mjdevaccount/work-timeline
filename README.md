# work-timeline

**Record every unit of work (a CI job, a deploy, a batch run) on one timeline, without letting the
recording break the work.**

[![ci](https://github.com/mjdevaccount/work-timeline/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/mjdevaccount/work-timeline/actions/workflows/ci.yml)
[![license](https://img.shields.io/github/license/mjdevaccount/work-timeline)](https://github.com/mjdevaccount/work-timeline/blob/main/LICENSE)

A timeline receiver keeps one row per unit of work. This package is the two things every writer
to it needs: the **contract** (a closed vocabulary and the request models the receiver validates
with) and a **writer** that opens a unit when the work starts, closes it when the work ends, and
never raises.

```python
from work_timeline import TimelineClient

sent: list[str] = []


def transport(url: str, body: bytes, headers: dict[str, str], timeout_s: float) -> tuple[int, bytes]:
    sent.append(url.rsplit("/", 1)[1])  # real use: omit `transport=` and the client uses urllib
    return 200, b'{"id": 1}'


timeline = TimelineClient("https://timeline.example.com", "test-key", service="ci-runner", transport=transport)

with timeline.recorded("nightly-build", branch="main") as unit:
    assert sent == ["open"]  # the unit is on the timeline while the build runs
    unit["artifacts"] = 3

assert sent == ["open", "close"]
```

## What the writer guarantees

- **Write on entry.** The unit is opened as `running` before the block runs, so a process killed
  mid-block leaves a unit that is still `running` instead of no row at all. If the open is not
  accepted, the close becomes one completion write. ([ADR-0001](docs/adr/0001-write-on-entry.md))
- **Never raises.** Each request is bounded by `timeout_s` and not retried; a failure is a `False`
  or `None` and one log line. The block's own exception is re-raised unchanged.
  ([ADR-0002](docs/adr/0002-the-writer-never-raises.md))
- **Cancelled is not failed.** `CancelledError`, `KeyboardInterrupt` and `SystemExit` close the
  unit as `cancelled`. ([ADR-0003](docs/adr/0003-cancelled-is-not-failed.md))
- **One contract.** The client builds each body through the models the receiver validates with,
  so it cannot send a field the receiver would drop. ([ADR-0004](docs/adr/0004-one-contract-for-receiver-and-writers.md))
- **Inert when unconfigured**, and **the API key is never logged**.

## Install

```bash
pip install "work-timeline @ https://github.com/mjdevaccount/work-timeline/releases/download/v0.3.0/work_timeline-0.3.0-py3-none-any.whl"
```

Each release attaches its wheel to a GitHub release; pin the wheel URL. The only runtime
dependency is pydantic.

## Configure from the environment

```{.python test="skip"}
from work_timeline import TimelineClient

timeline = TimelineClient.from_env(service="etl-worker")  # WORK_TIMELINE_BASE_URL, WORK_TIMELINE_API_KEY
if not timeline.configured:
    log.warning("work timeline disabled, missing %s", timeline.missing())
```

`from_env(base_var=..., key_var=...)` reads other variable names. The names used before 0.3.0
are still read when the current ones are unset, with one `FutureWarning`, until 1.0.0
([`CHANGELOG.md`](CHANGELOG.md)).

## From a shell script

A caller that is not Python uses the CLI, so its body goes through the same models:

```bash
WORK_TIMELINE_API_KEY="$key" python -m work_timeline record \
  --service ci-runner --kind deploy --name api \
  --started "$started" --ended "$(date -u +%FT%TZ)" --status ok \
  --ref deploys:api --attr env=staging --base-url https://timeline.example.com/api
```

`open` prints the new unit's id and `close --id N` finishes it; `--dry-run` prints the body and
sends nothing. The API key is read from the variable `--key-var` names, never from argv. Exit
codes keep the failures apart: `0` accepted, `2` bad input, `3` refused by the receiver, `4` no
response, `5` not configured. Translate your own status words before calling: anything other than
`ok`, `failed` or `cancelled` is recorded as `failed`.

## The contract

| module | what |
|---|---|
| `work_timeline.vocab` | the closed `KINDS`, `LAYERS` and `STATUSES`; `status_for(exc, http_status)`; `terminal()` (an unknown status becomes `failed`); `ERROR_MAX` |
| `work_timeline.contract` | `WorkOpen`, `WorkClose`, `WorkRecord` and the three paths they post to |
| `work_timeline.client` | `TimelineClient`: `open`, `close`, `record`, and `recorded()` / `arecorded()` around a block |
| `work_timeline.cli` | `python -m work_timeline` with `record`, `open` and `close` |

On the receiver, units live in a table named `ops.work`, one row per unit. A new kind, layer or
status ships to the **receiver first**: it refuses an unknown value with a 422 naming the allowed
set, so a writer released ahead of it would have its units refused.
([ADR-0005](docs/adr/0005-closed-vocabulary-receiver-first.md))

## Project

- [`CHANGELOG.md`](CHANGELOG.md): what changed, release by release.
- [`docs/adr/`](docs/adr/README.md): why the design is the way it is.
- [`CONTRIBUTING.md`](CONTRIBUTING.md): setup, docstring rules, releasing.

MIT licensed.
