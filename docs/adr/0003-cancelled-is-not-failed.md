---
status: accepted
date: 2026-11-03
---

# A stopped unit is `cancelled`, not `failed`

Decided in 0.1.0 (`vocab.status_for`). Recorded in 1.0.0.

## Context and problem statement

A deploy restarts workers; a shutdown cancels in-flight tasks; an operator presses Ctrl-C. In each
case the work was stopped, not broken. Before this package, writers reported only `ok` or
`failed`, so every routine restart painted the timeline red, and red stopped meaning anything. The
status `cancelled` existed in the receiver's vocabulary, and no writer could produce it.

`asyncio.CancelledError` derives from `BaseException`, not `Exception`. A handler that maps "any
exception" to `failed` therefore has to check cancellation first, or it never sees it.

## Considered options

1. Two outcomes, `ok` and `failed`.
2. A third outcome, `cancelled`, for `CancelledError`, `KeyboardInterrupt` and `SystemExit`.

## Decision outcome

Chosen option 2. `status_for(exc, http_status)` checks `CANCEL_EXCEPTIONS` before anything else,
then any other exception (`failed`), then an HTTP status of 400 or above (`failed`), else `ok`.
The context managers record the outcome and re-raise the exception unchanged.

A caller's own status words are coerced by `terminal()`: a word outside `ok`, `failed` and
`cancelled` becomes `failed`, the conservative member, and never passes through as a new state.

### Consequences

- Good: `failed` on the timeline means something broke.
- Neutral: a `SystemExit(0)` inside a recorded block is recorded as `cancelled`, since the block
  did not run to its end.
