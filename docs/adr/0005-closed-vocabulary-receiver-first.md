---
status: accepted
date: 2026-11-03
---

# Kinds, layers and statuses are closed sets; a new value ships to the receiver first

Decided in 0.1.0 (`work_timeline.vocab`). Recorded in 1.0.0.

## Context and problem statement

A timeline view groups and colours units by kind and status. If those were free text, a typo
would quietly create a new group, and an unknown status would render as nothing in particular.

## Considered options

1. Free-text kind and status.
2. Closed sets, validated by the receiver, owned in one module both sides import.

## Decision outcome

Chosen option 2. `KINDS`, `LAYERS` and `STATUSES` live in `vocab`. `TERMINAL` is derived from
`STATUSES` by removing `running`, so a new status reaches it without a second edit. The receiver
refuses a value outside a set with a 422 naming the allowed values; the client refuses an unknown
default kind at construction.

A receiver can pin `STATUSES` against its database constraint in its own integration tests, so
the tuple cannot drift from the schema either.

Adding a value is a deliberate edit here, released to the **receiver first**. A writer released
ahead of the receiver would have every unit using the new value refused.

### Consequences

- Good: the set of groups on the timeline is exactly the set in this module.
- Bad: a new kind needs a release of this package and a receiver deploy before any writer uses it.
