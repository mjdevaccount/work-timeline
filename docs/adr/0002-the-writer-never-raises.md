---
status: accepted
date: 2026-11-03
---

# The writer never raises, is bounded by a timeout, and does not retry

Decided in 0.1.0. Recorded in 0.3.0.

## Context and problem statement

Recording a unit is observation. If the act of observing can fail the work it observes, every
receiver outage becomes an outage of every writer. Two failure shapes matter:

- An endpoint that is down raises quickly. An endpoint that hangs does not raise: it blocks,
  and a writer without a bound waits as long as the socket allows.
- `recorded()` closes the unit from a `finally`. An exception raised by that close would replace
  the block's own exception, so the caller would see a serialisation error instead of the error
  that actually happened.

## Decision drivers

- A receiver outage must cost rows, never the work.
- The block's own exception must reach the caller unchanged.
- A row that arrives late is worth little; wall-clock spent on telemetry is taken from the work.

## Considered options

1. Raise on failure and let the caller decide.
2. Retry with backoff.
3. One bounded attempt; every failure becomes `False` or `None` plus one log line.

## Decision outcome

Chosen option 3. Every request is bounded by `timeout_s` and attempted once. Building the body,
serialising it and sending it all happen inside one guard, so a value whose `__str__` raises costs
that unit's row and nothing else. A value JSON cannot hold, such as a `Decimal`, is sent as its
string form rather than costing the row.

The log line names the request path, the outcome and, for a transport error, the exception class
only: a transport error's message can carry the request, and the request carries the API key in a
header.

With no base URL or no key the client is inert: every call returns at once. `configured` and
`missing()` exist so the caller can say so once at startup; an inert writer that nobody announces
is indistinguishable from one with nothing to record.

### Consequences

- Good: no receiver state can fail or stall a writer beyond `timeout_s` per request.
- Bad: a brief receiver outage loses the units written during it. A caller that needs delivery
  guarantees needs a queue, which is out of scope here.
