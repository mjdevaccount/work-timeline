"""`TimelineClient`: record units of work on a remote timeline receiver over HTTP.

Invariants:
    Write on entry. `recorded()` opens a `running` unit before the block runs and closes it
    afterwards, so a process killed mid-block leaves a unit that is still `running`. If the open
    is not accepted, the close becomes one completion write. Rationale: ADR-0001.

    Never raises. Every call is bounded by `timeout_s`, is not retried, and reports failure as
    `False` or `None` plus one log line. Serialisation happens inside that guard, so a value that
    cannot be encoded costs the unit, never the caller's own exception. Rationale: ADR-0002.

    Cancelled is not failed (`vocab.status_for`). Rationale: ADR-0003.

    Inert when unconfigured. With no base URL or no API key every call is a no-op; `configured`
    and `missing()` say so, for one log line at startup.

    The API key is never logged. A log line names the request path, the outcome and, for a
    transport error, the exception class only.

The default transport is the standard library's `urllib`, so the package adds no HTTP
dependency; pass `transport=` to use another client or a test double. The async context manager
runs each write on a worker thread.
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
import warnings
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any

from pydantic import BaseModel

from work_timeline import contract, vocab

__all__ = [
    "API_KEY_VAR",
    "BASE_URL_VAR",
    "DEFAULT_TIMEOUT_S",
    "LEGACY_ENV_VARS",
    "TimelineClient",
    "Transport",
    "Unit",
    "encode",
    "read_env",
    "urllib_transport",
]

log = logging.getLogger(__name__)

#: `(url, body, headers, timeout_s) -> (http_status, response_body)`. A transport may raise; the
#: client catches it.
Transport = Callable[[str, bytes, dict[str, str], float], tuple[int, bytes]]

#: Default bound on each request, in seconds.
DEFAULT_TIMEOUT_S = 4.0
#: Environment variable `TimelineClient.from_env` and the CLI read the receiver's base URL from.
BASE_URL_VAR = "WORK_TIMELINE_BASE_URL"
#: Environment variable `TimelineClient.from_env` and the CLI read the API key from.
API_KEY_VAR = "WORK_TIMELINE_API_KEY"
#: Deprecated names, still read when the current name is unset, with a `FutureWarning` once per
#: process per name. They will stop being read in 1.0.0.
LEGACY_ENV_VARS: dict[str, str] = {
    BASE_URL_VAR: "TRADE_DATA_BASE_URL",
    API_KEY_VAR: "TRADE_DATA_API_KEY",
}

_warned: set[str] = set()


def read_env(name: str) -> str:
    """Read an environment variable, falling back to its deprecated name.

    Args:
        name: The variable to read, for example `API_KEY_VAR`.

    Returns:
        The value of `name` when it is set and not empty; otherwise the value of its entry in
        `LEGACY_ENV_VARS`, if any; otherwise an empty string.

    Invariants:
        Reading a deprecated name emits one `FutureWarning` per process for that name. The
        warning names both variables and never the value.
    """
    value = os.environ.get(name, "")
    legacy = LEGACY_ENV_VARS.get(name)
    if value or legacy is None:
        return value
    value = os.environ.get(legacy, "")
    if value and legacy not in _warned:
        _warned.add(legacy)
        warnings.warn(
            f"{legacy} is deprecated and will stop being read in work-timeline 1.0.0; set {name} instead",
            FutureWarning,
            stacklevel=2,
        )
    return value


def urllib_transport(url: str, body: bytes, headers: dict[str, str], timeout_s: float) -> tuple[int, bytes]:
    """POST `body` to `url` with the standard library.

    Args:
        url: The full request URL.
        body: The JSON request body.
        headers: Request headers.
        timeout_s: Socket timeout, in seconds.

    Returns:
        The HTTP status and the response body. An HTTP error status is returned, not raised.

    Raises:
        OSError: When no response arrives (connection refused, DNS failure, timeout).
    """
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return int(resp.status), resp.read()
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read() or b""


def _default(o: Any) -> Any:
    return o.isoformat() if isinstance(o, dt.datetime | dt.date) else str(o)


def encode(model: BaseModel) -> bytes:
    """Serialise a contract model to its wire bytes.

    Args:
        model: A `WorkOpen`, `WorkClose` or `WorkRecord`.

    Returns:
        Compact JSON. Datetimes are ISO 8601; any other value JSON cannot hold (a `Decimal`, say)
        is sent as its `str()`.

    Raises:
        Exception: Whatever a value's `__str__` raises. `TimelineClient` catches it.
    """
    return json.dumps(model.model_dump(mode="python"), separators=(",", ":"), default=_default).encode()


class Unit(dict[str, Any]):
    """The attributes dict that `recorded()` yields, plus an outcome the block can set.

    Keys set on it are sent as the unit's attributes when it closes. An exception raised by the
    block always decides the status; without one, `fail()` or a `mark_http()` of 400 or above
    makes the unit `failed`.

    Attributes:
        status: The status the block set, or None.
        error: The error text the block set, or None.
    """

    def __init__(self, *a: Any, **kw: Any) -> None:
        super().__init__(*a, **kw)
        self.status: str | None = None
        self.error: str | None = None

    def fail(self, error: str | None = None) -> None:
        """Mark the unit `failed` without raising.

        Args:
            error: Error text, cut to `vocab.ERROR_MAX` characters.
        """
        self.status = "failed"
        self.error = error[: vocab.ERROR_MAX] if error else None

    def mark_http(self, status_code: int | None) -> None:
        """Record an HTTP status as the attribute `http_status`; 400 or above fails the unit.

        Args:
            status_code: The HTTP status the work ended with.
        """
        self["http_status"] = status_code
        if vocab.status_for(None, status_code) == "failed":
            self.fail(f"HTTP {status_code}")


class TimelineClient:
    """A writer that records units of work on a remote timeline receiver.

    Every unit's attributes carry `service`, and its `ref` defaults to `"<service>:<name>"`.

    Args:
        base_url: The receiver's base URL; the contract paths are appended to it.
        api_key: The key sent in `contract.API_KEY_HEADER`.
        service: The writer's name, for example `ci-runner`.
        kind: The default kind, one of `vocab.KINDS`.
        timeout_s: Bound on each request, in seconds.
        transport: The HTTP transport; `urllib_transport` when None.
        headers: Extra request headers, such as a `Host` header for a reverse proxy. The API key,
            `Content-Type` and `Accept` headers are set after these and cannot be replaced.

    Raises:
        ValueError: When `kind` is not in `vocab.KINDS`.
    """

    def __init__(
        self,
        base_url: str | None,
        api_key: str | None,
        *,
        service: str,
        kind: str = "job",
        timeout_s: float = DEFAULT_TIMEOUT_S,
        transport: Transport | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        if kind not in vocab.KINDS:
            raise ValueError(f"unknown kind {kind!r}; allowed: {sorted(vocab.KINDS)}")
        self._base = (base_url or "").strip().rstrip("/")
        self._key = (api_key or "").strip()
        self.service = service
        self.kind = kind
        self.timeout_s = timeout_s
        self._transport = transport or urllib_transport
        self._headers = dict(headers or {})

    @classmethod
    def from_env(
        cls, *, service: str, base_var: str = BASE_URL_VAR, key_var: str = API_KEY_VAR, **kw: Any
    ) -> TimelineClient:
        """Build a client from environment variables.

        Args:
            service: The writer's name.
            base_var: The variable holding the base URL. The default also falls back to its
                deprecated name (`read_env`).
            key_var: The variable holding the API key; falls back as `base_var` does.
            **kw: Passed to the constructor.

        Returns:
            A client, inert if either variable is unset or empty.
        """
        return cls(read_env(base_var), read_env(key_var), service=service, **kw)

    @property
    def configured(self) -> bool:
        """Whether both a base URL and an API key are set."""
        return bool(self._base and self._key)

    def missing(self) -> list[str]:
        """Name the settings that are absent.

        Returns:
            A subset of `["base_url", "api_key"]`; empty when the client is configured.
        """
        return [n for n, v in (("base_url", self._base), ("api_key", self._key)) if not v]

    # -- the three calls ----------------------------------------------------------------------

    def _post(self, path: str, build: Callable[[], BaseModel], what: str) -> tuple[int, bytes] | None:
        if not self.configured:
            return None
        try:
            body = encode(build())
            code, raw = self._transport(
                f"{self._base}{path}",
                body,
                {
                    **self._headers,
                    contract.API_KEY_HEADER: self._key,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                self.timeout_s,
            )
        except Exception as exc:
            # The class name only: a transport error's text can carry the request.
            log.warning(
                "work timeline unreachable (%s) - %s not written; the work is unaffected", type(exc).__name__, what
            )
            return None
        if code >= 400:
            log.warning("work timeline rejected %s at %s: http %s", what, path, code)
            return None
        return code, raw

    def _attrs(self, attrs: dict[str, Any] | None) -> dict[str, Any]:
        return {"service": self.service, **(attrs or {})}

    def open(
        self,
        name: str,
        *,
        started_at: dt.datetime,
        kind: str | None = None,
        ref: str | None = None,
        attrs: dict[str, Any] | None = None,
        layer: str = "process",
    ) -> int | None:
        """Open a `running` unit.

        Args:
            name: What is running.
            started_at: When it started; timezone-aware.
            kind: One of `vocab.KINDS`; the client's default when None.
            ref: A stable reference; `"<service>:<name>"` when None.
            attrs: Attributes to send.
            layer: One of `vocab.LAYERS`.

        Returns:
            The unit's id, or None when the client is inert, the receiver did not accept the
            open, or its reply carried no integer `id`. Never raises.
        """
        got = self._post(
            contract.OPEN_PATH,
            lambda: contract.WorkOpen(
                kind=kind or self.kind,
                name=name,
                started_at=started_at,
                layer=layer,
                ref=ref or f"{self.service}:{name}",
                attrs=self._attrs(attrs),
            ),
            f"open {name}",
        )
        if got is None:
            return None
        try:
            wid = json.loads(got[1].decode() or "null").get("id")
        except Exception:
            return None
        return wid if isinstance(wid, int) else None

    def close(
        self,
        work_id: int,
        *,
        ended_at: dt.datetime,
        status: str,
        error: str | None = None,
        attrs: dict[str, Any] | None = None,
    ) -> bool:
        """Close a unit returned by `open`.

        A refused close is not re-sent in any form: the unit stays `running` on the receiver,
        which is the accurate record of what the receiver knows.

        Args:
            work_id: The id `open` returned.
            ended_at: When the work ended; timezone-aware.
            status: The outcome, coerced with `vocab.terminal`.
            error: Error text, cut to `vocab.ERROR_MAX` characters.
            attrs: Attributes to send.

        Returns:
            Whether the receiver accepted the close. Never raises.
        """
        return (
            self._post(
                contract.CLOSE_PATH,
                lambda: contract.WorkClose(
                    id=work_id,
                    ended_at=ended_at,
                    status=vocab.terminal(status),
                    error=error[: vocab.ERROR_MAX] if error else None,
                    attrs=self._attrs(attrs),
                ),
                f"close {work_id}",
            )
            is not None
        )

    def record(
        self,
        name: str,
        *,
        started_at: dt.datetime,
        ended_at: dt.datetime,
        status: str,
        kind: str | None = None,
        ref: str | None = None,
        error: str | None = None,
        attrs: dict[str, Any] | None = None,
        layer: str = "process",
    ) -> bool:
        """Record one finished unit in a single write.

        Args:
            name: What ran.
            started_at: When it started; timezone-aware.
            ended_at: When it ended; timezone-aware.
            status: The outcome, coerced with `vocab.terminal`.
            kind: One of `vocab.KINDS`; the client's default when None.
            ref: A stable reference; `"<service>:<name>"` when None.
            error: Error text, cut to `vocab.ERROR_MAX` characters.
            attrs: Attributes to send.
            layer: One of `vocab.LAYERS`.

        Returns:
            Whether the receiver accepted the unit. Never raises.
        """
        return (
            self._post(
                contract.RECORD_PATH,
                lambda: contract.WorkRecord(
                    kind=kind or self.kind,
                    name=name,
                    started_at=started_at,
                    ended_at=ended_at,
                    status=vocab.terminal(status),
                    ref=ref or f"{self.service}:{name}",
                    error=error[: vocab.ERROR_MAX] if error else None,
                    attrs=self._attrs(attrs),
                    layer=layer,
                ),
                f"record {name}",
            )
            is not None
        )

    # -- around a block ------------------------------------------------------------------------

    @staticmethod
    def _outcome(unit: Unit, exc: BaseException | None) -> tuple[str, str | None]:
        if exc is not None:
            return vocab.status_for(exc), vocab.error_text(exc)
        return (unit.status or "ok"), unit.error

    def _finish(
        self,
        name: str,
        kind: str | None,
        wid: int | None,
        started: dt.datetime,
        unit: Unit,
        exc: BaseException | None,
    ) -> None:
        status, err = self._outcome(unit, exc)
        ended = dt.datetime.now(dt.UTC)
        if wid is not None:
            self.close(wid, ended_at=ended, status=status, error=err, attrs=dict(unit))
        else:
            self.record(name, kind=kind, started_at=started, ended_at=ended, status=status, error=err, attrs=dict(unit))

    @contextlib.contextmanager
    def recorded(self, name: str, *, kind: str | None = None, **attrs: Any) -> Iterator[Unit]:
        """Record the enclosed block as one unit: open on entry, close on exit.

        If the open is not accepted, the exit sends one completion write instead. An exception
        from the block is recorded and re-raised unchanged.

        Example:
            ```python
            with client.recorded("nightly-build", branch="main") as unit:
                unit["artifacts"] = build()
            ```

        Args:
            name: What runs.
            kind: One of `vocab.KINDS`; the client's default when None.
            **attrs: Initial attributes.

        Yields:
            A `Unit`: set keys on it to send them as attributes, or call `fail()` / `mark_http()`.
        """
        started = dt.datetime.now(dt.UTC)
        unit = Unit(attrs)
        wid = self.open(name, kind=kind, started_at=started, attrs=dict(unit))
        exc: BaseException | None = None
        try:
            yield unit
        except BaseException as e:  # re-raised; caught only to record the outcome
            exc = e
            raise
        finally:
            self._finish(name, kind, wid, started, unit, exc)

    @contextlib.asynccontextmanager
    async def arecorded(self, name: str, *, kind: str | None = None, **attrs: Any) -> AsyncIterator[Unit]:
        """Async form of `recorded`. Each write runs on a worker thread, so the event loop never waits on it.

        Args:
            name: What runs.
            kind: One of `vocab.KINDS`; the client's default when None.
            **attrs: Initial attributes.

        Yields:
            A `Unit`, as `recorded` does.
        """
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
