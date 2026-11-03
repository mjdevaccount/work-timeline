"""The closed vocabulary of a work unit: its kinds, layers and statuses, and the outcome mapping.

The receiver and every writer import these values from here, so a value cannot be spelled two
ways. Each set is closed: the receiver refuses a value outside it with a 422 that names the
allowed set.

Rationale: ADR-0003 (cancelled is not failed), ADR-0005 (a closed vocabulary, receiver first).
"""

from __future__ import annotations

import asyncio

__all__ = [
    "CANCEL_EXCEPTIONS",
    "ERROR_MAX",
    "KINDS",
    "LAYERS",
    "RUNNING",
    "STATUSES",
    "TERMINAL",
    "error_text",
    "status_for",
    "terminal",
]

#: What sort of work a unit is. A timeline view groups by kind, so the set is closed: a typo
#: would otherwise create a new group.
KINDS: frozenset[str] = frozenset(
    {
        "job",  # a scheduled or queued unit of work: a cron run, a batch step, an HTTP-triggered task
        "scan",  # one pass of a periodic scan over a set of targets
        "stream",  # one run of a long-lived stream consumer
        "daemon",  # one run of a long-lived worker process
        "deploy",  # one deployment, recorded by the deploying host
    }
)

#: Which tier of the writer spent the time.
LAYERS: tuple[str, ...] = ("process", "usecase", "repo", "external")

#: Every value a unit's status can hold.
STATUSES: tuple[str, ...] = ("running", "ok", "failed", "cancelled")

#: The one non-terminal status. A unit is `running` exactly while it has no end time.
RUNNING = "running"

#: Every finished status, derived from `STATUSES` so a new status reaches it without a second edit.
TERMINAL: tuple[str, ...] = tuple(s for s in STATUSES if s != RUNNING)

#: The maximum length of a unit's error text, enforced by the contract models and the client.
ERROR_MAX = 500

#: Exceptions that mean the work was stopped rather than that it failed.
CANCEL_EXCEPTIONS: tuple[type[BaseException], ...] = (asyncio.CancelledError, KeyboardInterrupt, SystemExit)


def status_for(exc: BaseException | None = None, http_status: int | None = None) -> str:
    """Map an outcome onto a terminal status.

    Args:
        exc: The exception the work ended with, if any.
        http_status: The HTTP status the work ended with, if it was a request.

    Returns:
        `cancelled` for any of `CANCEL_EXCEPTIONS`; `failed` for any other exception, or for an
        HTTP status of 400 or above; otherwise `ok`.

    Invariants:
        Cancellation is checked first: `asyncio.CancelledError` derives from `BaseException`, so a
        broad handler would otherwise report a stopped unit as `failed`. Rationale: ADR-0003.
    """
    if isinstance(exc, CANCEL_EXCEPTIONS):
        return "cancelled"
    if exc is not None:
        return "failed"
    if http_status is not None and http_status >= 400:
        return "failed"
    return "ok"


def terminal(status: str) -> str:
    """Coerce a caller's status onto `TERMINAL`.

    Args:
        status: A status word supplied by the caller.

    Returns:
        `status` when it is in `TERMINAL`; otherwise `failed`, the conservative member. An
        unknown word never passes through as a new state.
    """
    return status if status in TERMINAL else "failed"


def error_text(exc: BaseException) -> str:
    """Render an exception as one capped line of error text.

    Args:
        exc: The exception to render.

    Returns:
        `"<TypeName>: <message>"`, cut to `ERROR_MAX` characters.
    """
    return f"{type(exc).__name__}: {exc}"[:ERROR_MAX]
