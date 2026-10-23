# work-timeline

The `ops.work` contract and the one remote writer for it.

A service that does work outside the process that owns the timeline (a quant backfill, a bank
sync, a deploy) puts that work on the shared day view over HTTP. Before this package each such
service re-typed the vocabulary and its own client, and the copies drifted: one posted
`success` and 500'd the receiver, all of them collapsed `cancelled` into `failed`, and one wrote
only on completion, so a job that crashed left no row at all.

| module | what |
|---|---|
| `work_timeline.vocab` | closed `KINDS` / `LAYERS` / `STATUSES`, `status_for(exc, http_status)` (cancelled is not failed), `terminal()` (unknown -> `failed`), `ERROR_MAX` |
| `work_timeline.contract` | `WorkOpen` / `WorkClose` / `WorkRecord`: the models the **receiver validates with** and the client **builds through**, plus the three paths |
| `work_timeline.client` | `TimelineClient`: `open` / `close` / `record`, and `recorded()` / `arecorded()` around a block |

```python
from work_timeline import TimelineClient

timeline = TimelineClient.from_env(service="finance-ops")   # TRADE_DATA_BASE_URL / TRADE_DATA_API_KEY
with timeline.recorded("bank_sync", provider="simplefin") as w:
    w["txns"] = sync()
```

Rules the client holds: **write on entry** (open a `running` row, close it after; a failed open
falls back to one completion write), **never raises** and is bounded by `timeout_s`,
**cancelled is not failed**, serialisation happens inside the guard (a `Decimal` attr is sent as
a string), **inert when unconfigured**, and the key is never logged. Transport is stdlib urllib;
inject your own with `transport=`.

## Install

Pinned to a CI-built release wheel (immutable bytes, no git CLI needed):

```toml
"work-timeline @ https://github.com/mjdevaccount/work-timeline/releases/download/v0.1.1/work_timeline-0.1.1-py3-none-any.whl"
```

A new kind, layer or status ships to the **receiver first**: it refuses an unknown value with a
422 naming the allowed set, and a writer pinned ahead of it would have its rows refused.
