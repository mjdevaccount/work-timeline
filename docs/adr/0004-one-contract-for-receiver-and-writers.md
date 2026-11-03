---
status: accepted
date: 2026-11-03
---

# The receiver validates with, and every writer builds through, the same models

Decided in 0.1.0 (`work_timeline.contract`). Recorded in 0.3.0.

## Context and problem statement

Before this package, the receiver owned the request models and each writer re-typed the subset it
used: its own field names, its own status words, its own JSON building. The copies drifted in ways
no single test could see:

- The receiver's finished-unit model had no `error` field. Pydantic dropped the key from every
  failure row and answered 200, while each writer's own suite asserted on a field that never
  landed.
- A shell writer posted the status `success`, which the receiver did not know.

A test on either side passed, because each side tested against its own copy.

## Decision drivers

- A writer must not be able to send a field the receiver drops.
- A shell writer must not have to re-implement the body.

## Considered options

1. Document the wire format and let each writer implement it.
2. One package holds the models; the receiver validates with them and the client builds through
   them.

## Decision outcome

Chosen option 2. `WorkOpen`, `WorkClose` and `WorkRecord` are the receiver's request models. The
client constructs each body through them, so a field the model lacks fails at construction on the
writer, not silently on the receiver. Shell writers use the CLI (ADR-0006), which builds through
the same models.

The models carry shape and length caps. Closed-vocabulary checks stay in the receiver's handlers,
where a refusal is a 422 that names the allowed set (ADR-0005).

### Consequences

- Good: a receiver-side model change reaches writers through a version bump, not a re-typing.
- Bad: receiver and writers share a release cadence for model changes.
