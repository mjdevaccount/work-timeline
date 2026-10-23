"""Put a unit of work on the shared timeline from outside the receiving process.

THE RULES THIS CLIENT EXISTS TO HOLD, each one learned from a copy that broke it:

* WRITE ON ENTRY. `recorded()` opens a `running` row before the work starts and closes it after,
  so a process killed mid-run (OOM, SIGKILL, a reboot) leaves a row with an old `started_at`,
  which is exactly the shape of "this died". A writer that posts only on completion makes "it
  never ran" and "it died" the same absence. If the open fails, the close falls back to one
  completion write, so adopting open/close can never lose a row the old path would have kept.
* NEVER RAISES, NEVER BLOCKS LONG. Observation must not break the work it observes: every call
  is bounded by `timeout_s` (a wedged endpoint does not raise, it BLOCKS) and swallows every
  failure into a `False`/`None` and one log line. Not retried: a row a few seconds late is
  worth nothing, and a retry spends the job's wall-clock on telemetry.
* CANCELLED IS NOT FAILED (`vocab.status_for`).
* SERIALISATION IS INSIDE THE GUARD. `recorded()` closes from a `finally`, so an exception
  escaping the write would REPLACE the job's real exception. Non-JSON attrs (a Decimal) are
  sent as strings rather than costing the row.
* INERT, NOT HALF-WIRED. With no base URL or no key every call is a no-op returning
  `False`/`None`; `configured` says which, so the caller can log it once at startup.
* THE KEY IS NEVER LOGGED. Only the request path is.

Transport is stdlib urllib so a consumer grows no runtime dependency for two POSTs; tests and
callers inject their own with `transport=`. The async methods run the same call on a thread.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import json
import logging
import os
import urllib.error
import urllib.request
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any

from pydantic import BaseModel

from work_timeline import contract, vocab

log = logging.getLogger(__name__)

#: (url, body, headers, timeout_s) -> (http_status, response_body). Never sees an exception it
#: should hide: the client wraps the call.
Transport = Callable[[str, bytes, dict[str, str], float], tuple[int, bytes]]

DEFAULT_TIMEOUT_S = 4.0
BASE_URL_VAR = "TRADE_DATA_BASE_URL"
API_KEY_VAR = "TRADE_DATA_API_KEY"


def urllib_transport(url: str, body: bytes, headers: dict[str, str], timeout_s: float) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return int(resp.status), resp.read()
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read() or b""


def _default(o: Any) -> Any:
    return o.isoformat() if isinstance(o, dt.datetime | dt.date) else str(o)


def encode(model: BaseModel) -> bytes:
    """The wire bytes for one contract model. Datetimes as ISO 8601; anything else non-JSON as str."""
    return json.dumps(model.model_dump(mode="python"), separators=(",", ":"), default=_default).encode()


class Unit(dict[str, Any]):
    """The attrs dict `recorded()` yields, plus an outcome the body can set without raising.

    An exception always wins (it is what actually happened); otherwise `fail()` or a 4xx/5xx
    from `mark_http()` makes the unit `failed`.
    """

    def __init__(self, *a: Any, **kw: Any) -> None:
        super().__init__(*a, **kw)
        self.status: str | None = None
        self.error: str | None = None

    def fail(self, error: str | None = None) -> None:
        self.status = "failed"
        self.error = error[: vocab.ERROR_MAX] if error else None

    def mark_http(self, status_code: int | None) -> None:
        self["http_status"] = status_code
        if vocab.status_for(None, status_code) == "failed":
            self.fail(f"HTTP {status_code}")


class TimelineClient:
    """One remote writer. `service` tags every row's attrs and its default `ref`."""

    def __init__(self, base_url: str | None, api_key: str | None, *, service: str, kind: str = "job",
                 timeout_s: float = DEFAULT_TIMEOUT_S, transport: Transport | None = None) -> None:
        if kind not in vocab.KINDS:
            raise ValueError(f"unknown kind {kind!r}; allowed: {sorted(vocab.KINDS)}")
        self._base = (base_url or "").strip().rstrip("/")
        self._key = (api_key or "").strip()
        self.service = service
        self.kind = kind
        self.timeout_s = timeout_s
        self._transport = transport or urllib_transport

    @classmethod
    def from_env(cls, *, service: str, base_var: str = BASE_URL_VAR, key_var: str = API_KEY_VAR,
                 **kw: Any) -> TimelineClient:
        return cls(os.environ.get(base_var), os.environ.get(key_var), service=service, **kw)

    @property
    def configured(self) -> bool:
        return bool(self._base and self._key)

    def missing(self) -> list[str]:
        """Which half is absent, for a caller's one startup log line."""
        return [n for n, v in (("base_url", self._base), ("api_key", self._key)) if not v]

    # -- the three calls ----------------------------------------------------------------------

    def _post(self, path: str, build: Callable[[], BaseModel], what: str) -> tuple[int, bytes] | None:
        if not self.configured:
            return None
        try:
            body = encode(build())
            code, raw = self._transport(
                f"{self._base}{path}", body,
                {contract.API_KEY_HEADER: self._key, "Content-Type": "application/json",
                 "Accept": "application/json"},
                self.timeout_s)
        except Exception as exc:
            # Class name only: a transport error's text can carry the request.
            log.warning("work timeline unreachable (%s) - %s not written; the work is unaffected",
                        type(exc).__name__, what)
            return None
        if code >= 400:
            log.warning("work timeline rejected %s at %s: http %s", what, path, code)
            return None
        return code, raw

    def _attrs(self, attrs: dict[str, Any] | None) -> dict[str, Any]:
        return {"service": self.service, **(attrs or {})}

    def open(self, name: str, *, started_at: dt.datetime, kind: str | None = None, ref: str | None = None,
             attrs: dict[str, Any] | None = None, layer: str = "process") -> int | None:
        """Open a `running` row; its id, or None when the timeline could not take it."""
        got = self._post(contract.OPEN_PATH, lambda: contract.WorkOpen(
            kind=kind or self.kind, name=name, started_at=started_at, layer=layer,
            ref=ref or f"{self.service}:{name}", attrs=self._attrs(attrs)), f"open {name}")
        if got is None:
            return None
        try:
            wid = json.loads(got[1].decode() or "null").get("id")
        except Exception:
            return None
        return wid if isinstance(wid, int) else None

    def close(self, work_id: int, *, ended_at: dt.datetime, status: str, error: str | None = None,
              attrs: dict[str, Any] | None = None) -> bool:
        """Close a row from `open`. A 404 is the receiver saying nothing was updated: the row
        stays `running`, which is the honest record, and nothing is re-sent."""
        return self._post(contract.CLOSE_PATH, lambda: contract.WorkClose(
            id=work_id, ended_at=ended_at, status=vocab.terminal(status),
            error=error[: vocab.ERROR_MAX] if error else None, attrs=self._attrs(attrs)),
            f"close {work_id}") is not None

    def record(self, name: str, *, started_at: dt.datetime, ended_at: dt.datetime, status: str,
               kind: str | None = None, ref: str | None = None, error: str | None = None,
               attrs: dict[str, Any] | None = None, layer: str = "process") -> bool:
        """One FINISHED unit in a single write; whether it landed."""
        return self._post(contract.RECORD_PATH, lambda: contract.WorkRecord(
            kind=kind or self.kind, name=name, started_at=started_at, ended_at=ended_at,
            status=vocab.terminal(status), ref=ref or f"{self.service}:{name}",
            error=error[: vocab.ERROR_MAX] if error else None, attrs=self._attrs(attrs), layer=layer),
            f"record {name}") is not None

    # -- around a block ------------------------------------------------------------------------

    @staticmethod
    def _outcome(unit: Unit, exc: BaseException | None) -> tuple[str, str | None]:
        if exc is not None:
            return vocab.status_for(exc), vocab.error_text(exc)
        return (unit.status or "ok"), unit.error

    def _finish(self, name: str, kind: str | None, wid: int | None, started: dt.datetime,
                unit: Unit, exc: BaseException | None) -> None:
        status, err = self._outcome(unit, exc)
        ended = dt.datetime.now(dt.UTC)
        if wid is not None:
            self.close(wid, ended_at=ended, status=status, error=err, attrs=dict(unit))
        else:
            self.record(name, kind=kind, started_at=started, ended_at=ended, status=status, error=err,
                        attrs=dict(unit))

    @contextlib.contextmanager
    def recorded(self, name: str, *, kind: str | None = None, **attrs: Any) -> Iterator[Unit]:
        """Record the block: open on entry, close on exit, completion write if the open failed.

            with client.recorded("bank_sync", provider="simplefin") as w:
                w["txns"] = do_the_sync()
        """
        started = dt.datetime.now(dt.UTC)
        unit = Unit(attrs)
        wid = self.open(name, kind=kind, started_at=started, attrs=dict(unit))
        exc: BaseException | None = None
        try:
            yield unit
        except BaseException as e:      # re-raised; caught only to record the outcome
            exc = e
            raise
        finally:
            self._finish(name, kind, wid, started, unit, exc)

    @contextlib.asynccontextmanager
    async def arecorded(self, name: str, *, kind: str | None = None, **attrs: Any) -> AsyncIterator[Unit]:
        """`recorded` for async code; each write runs on a thread so the loop never blocks on it."""
        started = dt.datetime.now(dt.UTC)
        unit = Unit(attrs)
        wid = await asyncio.to_thread(self.open, name, kind=kind, started_at=started, attrs=dict(unit))
        exc: BaseException | None = None
        try:
            yield unit
        except BaseException as e:
            exc = e
            raise
        finally:
            with contextlib.suppress(Exception):
                await asyncio.to_thread(self._finish, name, kind, wid, started, unit, exc)
