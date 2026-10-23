"""The wire contract: three request bodies and the paths they post to.

THE RECEIVER VALIDATES WITH THESE SAME MODELS, and the client BUILDS its payload through them.
That is the point of the package. `WorkRecord` once had no `error` field; pydantic dropped the
key on every remote failure row while answering 200, and both writer suites asserted a field
that never landed. A writer that builds through the receiver's model cannot send what it drops.

Closed-vocabulary checks (kind, layer, status) stay in the receiver's handlers, where a refusal
is a 422 naming the allowed set; the models carry the shape and the caps.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import BaseModel, Field

from work_timeline.vocab import ERROR_MAX

OPEN_PATH = "/admin/work/open"
CLOSE_PATH = "/admin/work/close"
#: NOT under /admin/run/: the receiver's timeline middleware wraps that prefix, so posting there
#: would file a row for the act of reporting beside the row being reported.
RECORD_PATH = "/admin/work/record"

#: The header the receiver's API-key authenticator reads.
API_KEY_HEADER = "X-API-Key"

TRACE_MAX = 64
SPAN_MAX = 32


class WorkRecord(BaseModel):
    """A FINISHED unit of work performed outside the receiving process."""

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
    """Start a unit that is still RUNNING: the half WorkRecord cannot express."""

    kind: str
    name: str
    started_at: dt.datetime
    layer: str = "process"
    ref: str | None = None
    attrs: dict[str, Any] = Field(default_factory=dict)
    trace_id: str | None = Field(default=None, max_length=TRACE_MAX)
    span_id: str | None = Field(default=None, max_length=SPAN_MAX)


class WorkClose(BaseModel):
    """Finish a unit opened through OPEN_PATH."""

    id: int
    ended_at: dt.datetime
    status: str = "ok"
    error: str | None = Field(default=None, max_length=ERROR_MAX)
    attrs: dict[str, Any] = Field(default_factory=dict)
