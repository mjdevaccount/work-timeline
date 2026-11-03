"""The `ops.work` vocabulary, owned in ONE place for the receiver and every writer.

Before this package, trade-data held the vocabulary and three writers (trade-quant,
finance-ops, edge-host) each re-typed the subset they used. Two drifts came out of that:
edge-host posted `success`, which the receiver refused while `failed` happened to overlap; and
every writer collapsed `cancelled` into `failed`, so a routine deploy painted the timeline red.

trade-data pins `STATUSES` against the live `work_status_known` CHECK (mig268) in its
integration suite, so this tuple cannot drift from the schema either.
"""

from __future__ import annotations

import asyncio

#: What sort of work. CLOSED: the day view groups by it, so a typo would quietly create a
#: category. Adding one is a deliberate edit here plus a receiver deploy before any writer uses it.
KINDS: frozenset[str] = frozenset({
    "job",      # a queued unit or an /admin/run/* request: scheduled work
    "scan",     # one strategy scan cycle over a symbol
    "stream",   # one streamer process run
    "daemon",   # one daemon process run
    "deploy",   # one deploy, recorded from the host
})

#: Which tier served the time. Closed for the same reason as KINDS.
LAYERS: tuple[str, ...] = ("process", "usecase", "repo", "external")

#: Every value `ops.work.status` can hold.
STATUSES: tuple[str, ...] = ("running", "ok", "failed", "cancelled")

#: The one non-terminal value; the schema ties it to `ended_at IS NULL`.
RUNNING = "running"

#: Every FINISHED value, derived by subtraction so a new status reaches it without a second edit.
TERMINAL: tuple[str, ...] = tuple(s for s in STATUSES if s != RUNNING)

#: The cap on an error message, applied by the receiver's model AND by the client.
ERROR_MAX = 500

#: Exceptions that mean the work was STOPPED, not that it failed. A deploy that stops a job
#: mid-run is the estate's most common event; recording it as `failed` makes red mean nothing.
CANCEL_EXCEPTIONS: tuple[type[BaseException], ...] = (
    asyncio.CancelledError, KeyboardInterrupt, SystemExit)


def status_for(exc: BaseException | None = None, http_status: int | None = None) -> str:
    """Translate an outcome into the closed set at the boundary.

    Cancelled before failed (CancelledError is a BaseException, so a broad handler would
    swallow it into `failed`); an HTTP 4xx/5xx with no exception is `failed`; else `ok`.
    """
    if isinstance(exc, CANCEL_EXCEPTIONS):
        return "cancelled"
    if exc is not None:
        return "failed"
    if http_status is not None and http_status >= 400:
        return "failed"
    return "ok"


def terminal(status: str) -> str:
    """A caller's status coerced onto TERMINAL. An unknown value maps to the CONSERVATIVE
    member, `failed`, never to an invented state (`success` once 500'd the receiver)."""
    return status if status in TERMINAL else "failed"


def error_text(exc: BaseException) -> str:
    """`Type: message`, capped. A row is read in a list view; an error is a message, not a payload."""
    return f"{type(exc).__name__}: {exc}"[:ERROR_MAX]
