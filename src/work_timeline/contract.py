"""The wire contract: three request models and the paths they are posted to.

The receiver validates each request body with these models, and the client builds each body
through them, so a writer cannot send a field the receiver would drop. The models carry the shape
and the length caps; the closed-vocabulary checks on `kind`, `layer` and `status` belong to the
receiver, which answers a value outside `vocab` with a 422 naming the allowed set.

Rationale: ADR-0004.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import BaseModel, Field

from work_timeline.vocab import ERROR_MAX

__all__ = [
    "API_KEY_HEADER",
    "CLOSE_PATH",
    "OPEN_PATH",
    "RECORD_PATH",
    "SPAN_MAX",
    "TRACE_MAX",
    "WorkClose",
    "WorkOpen",
    "WorkRecord",
]

#: Path for `WorkOpen`: start a unit that is still running.
OPEN_PATH = "/admin/work/open"
#: Path for `WorkClose`: finish a unit opened through `OPEN_PATH`.
CLOSE_PATH = "/admin/work/close"
#: Path for `WorkRecord`: one finished unit in a single write. It sits outside `/admin/run/`, so a
#: receiver that times its own `/admin/run/*` requests does not also time the act of recording.
RECORD_PATH = "/admin/work/record"

#: The request header that carries the API key.
API_KEY_HEADER = "X-API-Key"

#: Maximum length of a trace id.
TRACE_MAX = 64
#: Maximum length of a span id.
SPAN_MAX = 32


class WorkRecord(BaseModel):
    """A finished unit of work, sent in a single write.

    Attributes:
        kind: One of `vocab.KINDS`.
        name: What ran, for example `nightly-build`.
        started_at: When the work started; timezone-aware.
        ended_at: When the work ended; timezone-aware.
        status: One of `vocab.TERMINAL`.
        ref: A stable reference to the thing that ran, for example `ci:nightly-build`.
        attrs: Free-form JSON attributes.
        error: Error text, at most `vocab.ERROR_MAX` characters.
        layer: One of `vocab.LAYERS`.
        trace_id: A distributed-trace id, at most `TRACE_MAX` characters.
        span_id: A span id, at most `SPAN_MAX` characters.
    """

    kind: str
    name: str
    started_at: dt.datetime
    ended_at: dt.datetime
    status: str = "ok"
    ref: str | None = None
    attrs: dict[str, Any] = Field(default_factory=dict)
    error: str | None = Field(default=None, max_length=ERROR_MAX)
    layer: str = "process"
    trace_id: str | None = Field(default=None, max_length=TRACE_MAX)
    span_id: str | None = Field(default=None, max_length=SPAN_MAX)


class WorkOpen(BaseModel):
    """A unit of work that has started and is still running.

    The receiver answers with the new unit's integer `id`, which `WorkClose` sends back.

    Attributes:
        kind: One of `vocab.KINDS`.
        name: What is running.
        started_at: When the work started; timezone-aware.
        layer: One of `vocab.LAYERS`.
        ref: A stable reference to the thing that is running.
        attrs: Free-form JSON attributes.
        trace_id: A distributed-trace id, at most `TRACE_MAX` characters.
        span_id: A span id, at most `SPAN_MAX` characters.
    """

    kind: str
    name: str
    started_at: dt.datetime
    layer: str = "process"
    ref: str | None = None
    attrs: dict[str, Any] = Field(default_factory=dict)
    trace_id: str | None = Field(default=None, max_length=TRACE_MAX)
    span_id: str | None = Field(default=None, max_length=SPAN_MAX)


class WorkClose(BaseModel):
    """The end of a unit opened with `WorkOpen`.

    Attributes:
        id: The id the receiver returned for the open.
        ended_at: When the work ended; timezone-aware.
        status: One of `vocab.TERMINAL`.
        error: Error text, at most `vocab.ERROR_MAX` characters.
        attrs: Free-form JSON attributes known at the end of the work.

    A receiver that finds no open unit with this `id` (already closed, pruned, or never opened)
    answers 404 and updates nothing.
    """

    id: int
    ended_at: dt.datetime
    status: str = "ok"
    error: str | None = Field(default=None, max_length=ERROR_MAX)
    attrs: dict[str, Any] = Field(default_factory=dict)
