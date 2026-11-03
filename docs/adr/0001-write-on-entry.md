---
status: accepted
date: 2026-11-03
---

# Open a unit when the work starts, close it when the work ends

Decided in 0.1.0 (`open`, `close`, `recorded()`). Recorded in 1.0.0.

## Context and problem statement

A writer that posts one row when the work finishes records nothing for work that never finishes:
a process killed by the OOM killer, a `SIGKILL`, a host reboot. On the timeline, "it never ran"
and "it died halfway" then look the same: an absence. Absences are what nobody notices.

## Decision drivers

- A unit that died must leave evidence that it started.
- Adopting the open/close protocol must never lose a row that a single completion write would
  have kept.
- One unit must never produce two rows.

## Considered options

1. One completion write per unit.
2. Open a `running` unit on entry, close it on exit.
3. Option 2, plus a completion write when the open was not accepted.

## Decision outcome

Chosen option 3. `recorded()` opens a `running` unit before the block runs and closes it from a
`finally`. A unit whose process dies stays `running` with an old `started_at`, which is exactly
the shape of "this died" and is what a stale-unit check on the receiver looks for.

If the open is not accepted (receiver unreachable, refused, or a reply with no integer `id`), the
exit sends one `WorkRecord` instead, so the unit is recorded as a single completion write would
have recorded it.

A refused close is not re-sent as a record. A 404 on close means the receiver has no open unit
with that id (already closed, pruned, or never opened); a fallback write would add a second row
for the same unit.

### Consequences

- Good: a killed process leaves a `running` unit, visible to a staleness check.
- Good: the fallback keeps every row the completion-only protocol would have kept.
- Bad: two requests per unit instead of one.
