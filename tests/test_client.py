from __future__ import annotations

import asyncio
import datetime as dt
import decimal
import json
import logging
from typing import Any, ClassVar

import pytest

from work_timeline import TimelineClient, WorkClose, WorkOpen, WorkRecord, vocab
from work_timeline.contract import CLOSE_PATH, OPEN_PATH, RECORD_PATH

T0 = dt.datetime(2026, 10, 23, 14, 0, tzinfo=dt.UTC)
T1 = dt.datetime(2026, 10, 23, 14, 5, tzinfo=dt.UTC)


class Wire:
    """A fake receiver: answers each path, keeps every request, and parses each body with the
    SAME model the real receiver uses."""

    MODELS: ClassVar[dict[str, type]] = {OPEN_PATH: WorkOpen, CLOSE_PATH: WorkClose, RECORD_PATH: WorkRecord}

    def __init__(self, *, open_status: int = 200, close_status: int = 200, record_status: int = 200,
                 raise_on: str | None = None, open_id: Any = 41) -> None:
        self.codes = {OPEN_PATH: open_status, CLOSE_PATH: close_status, RECORD_PATH: record_status}
        self.raise_on = raise_on
        self.open_id = open_id
        self.calls: list[tuple[str, dict[str, Any], dict[str, str], float]] = []

    def __call__(self, url: str, body: bytes, headers: dict[str, str], timeout_s: float) -> tuple[int, bytes]:
        path = "/" + url.split("/", 3)[3]
        path = path[path.index("/admin"):]
        if self.raise_on == path:
            raise TimeoutError("blackholed")
        payload = json.loads(body)
        self.MODELS[path](**payload)              # the receiver's own validation
        self.calls.append((path, payload, headers, timeout_s))
        reply = {"id": self.open_id} if path == OPEN_PATH else {"ok": True}
        return self.codes[path], json.dumps(reply).encode()

    def paths(self) -> list[str]:
        return [c[0] for c in self.calls]


def _client(wire: Wire, **kw: Any) -> TimelineClient:
    return TimelineClient("http://td.test/api/", "k3y", service="trade-quant", transport=wire, **kw)


def test_recorded_opens_on_entry_and_closes_ok() -> None:
    wire = Wire()
    with _client(wire).recorded("pull_ohlcv", symbols=3) as w:
        assert wire.paths() == [OPEN_PATH]          # the row exists WHILE the work runs
        w["rows"] = 120
    assert wire.paths() == [OPEN_PATH, CLOSE_PATH]
    opened, closed = wire.calls[0][1], wire.calls[1][1]
    assert opened["kind"] == "job" and opened["ref"] == "trade-quant:pull_ohlcv"
    assert opened["attrs"] == {"service": "trade-quant", "symbols": 3}
    assert closed["id"] == 41 and closed["status"] == "ok"
    assert closed["attrs"] == {"service": "trade-quant", "symbols": 3, "rows": 120}


def test_the_url_is_joined_once_and_the_key_rides_the_header() -> None:
    wire = Wire()
    _client(wire).record("x", started_at=T0, ended_at=T1, status="ok")
    path, _, headers, _ = wire.calls[0]
    assert path == RECORD_PATH and headers["X-API-Key"] == "k3y"


def test_a_failed_open_falls_back_to_one_completion_write() -> None:
    wire = Wire(raise_on=OPEN_PATH)
    with _client(wire).recorded("pull_ohlcv"):
        pass
    assert wire.paths() == [RECORD_PATH]
    body = wire.calls[0][1]
    assert body["status"] == "ok" and body["started_at"] <= body["ended_at"]


@pytest.mark.parametrize("open_id", [None, "41", 4.1])
def test_an_open_reply_without_an_int_id_falls_back(open_id: Any) -> None:
    wire = Wire(open_id=open_id)
    with _client(wire).recorded("x"):
        pass
    assert wire.paths() == [OPEN_PATH, RECORD_PATH]


def test_an_exception_closes_failed_and_is_reraised_unchanged() -> None:
    wire = Wire()
    with pytest.raises(ValueError, match="boom"), _client(wire).recorded("x"):
        raise ValueError("boom")
    closed = wire.calls[-1][1]
    assert closed["status"] == "failed" and closed["error"] == "ValueError: boom"


@pytest.mark.parametrize("exc", [KeyboardInterrupt(), SystemExit(0), asyncio.CancelledError()])
def test_cancelled_is_not_failed(exc: BaseException) -> None:
    wire = Wire()
    with pytest.raises(type(exc)), _client(wire).recorded("x"):
        raise exc
    assert wire.calls[-1][1]["status"] == "cancelled"


def test_the_body_can_fail_the_unit_without_raising() -> None:
    wire = Wire()
    with _client(wire).recorded("x") as w:
        w.mark_http(503)
    closed = wire.calls[-1][1]
    assert closed["status"] == "failed" and closed["error"] == "HTTP 503"
    assert closed["attrs"]["http_status"] == 503


def test_a_2xx_mark_stays_ok() -> None:
    wire = Wire()
    with _client(wire).recorded("x") as w:
        w.mark_http(204)
    assert wire.calls[-1][1]["status"] == "ok"


def test_an_unknown_status_maps_to_failed_never_an_invented_state() -> None:
    wire = Wire()
    _client(wire).record("x", started_at=T0, ended_at=T1, status="success")
    assert wire.calls[0][1]["status"] == "failed"


def test_errors_are_capped_at_the_writer_too() -> None:
    wire = Wire()
    _client(wire).record("x", started_at=T0, ended_at=T1, status="failed", error="e" * 5000)
    assert len(wire.calls[0][1]["error"]) == vocab.ERROR_MAX


def test_a_decimal_attr_reaches_the_wire_as_a_string() -> None:
    wire = Wire()
    with _client(wire).recorded("x") as w:
        w["total"] = decimal.Decimal("1234.56")
    assert wire.calls[-1][1]["attrs"]["total"] == "1234.56"


def test_an_unserialisable_attr_costs_the_row_not_the_job() -> None:
    class Bad:
        def __str__(self) -> str:
            raise RuntimeError("no")

    wire = Wire()
    with pytest.raises(ValueError, match="the real one"), _client(wire).recorded("x") as w:
        w["bad"] = Bad()
        raise ValueError("the real one")              # must NOT be replaced by the write's error


@pytest.mark.parametrize("code", [401, 404, 422, 500])
def test_a_rejection_returns_false_and_never_raises(code: int) -> None:
    wire = Wire(record_status=code)
    assert _client(wire).record("x", started_at=T0, ended_at=T1, status="ok") is False


def test_a_rejected_close_is_not_resent_as_a_record() -> None:
    """A 404 close means the row is pruned or already closed; a fallback write would add a
    second row for one unit."""
    wire = Wire(close_status=404)
    with _client(wire).recorded("x"):
        pass
    assert wire.paths() == [OPEN_PATH, CLOSE_PATH]


@pytest.mark.parametrize(("base", "key"), [("", "k"), ("http://x", ""), (None, None)])
def test_unconfigured_is_inert(base: str | None, key: str | None) -> None:
    calls: list[Any] = []
    c = TimelineClient(base, key, service="s", transport=lambda *a: calls.append(a) or (200, b"{}"))
    assert not c.configured and c.missing()
    with c.recorded("x"):
        pass
    assert c.open("x", started_at=T0) is None
    assert c.record("x", started_at=T0, ended_at=T1, status="ok") is False
    assert calls == []


def test_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRADE_DATA_BASE_URL", "http://td.test")
    monkeypatch.setenv("TRADE_DATA_API_KEY", "k")
    assert TimelineClient.from_env(service="finance-ops").configured


def test_an_unknown_client_kind_is_refused_at_construction() -> None:
    with pytest.raises(ValueError, match="unknown kind"):
        TimelineClient("http://x", "k", service="s", kind="ingest")


def test_the_key_is_never_logged(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    with _client(Wire(raise_on=OPEN_PATH, record_status=500)).recorded("x"):
        pass
    assert caplog.records and "k3y" not in caplog.text


def test_the_timeout_reaches_the_transport() -> None:
    wire = Wire()
    _client(wire, timeout_s=2.0).record("x", started_at=T0, ended_at=T1, status="ok")
    assert wire.calls[0][3] == 2.0


async def test_arecorded_opens_closes_and_survives_cancel() -> None:
    wire = Wire()
    async with _client(wire).arecorded("x") as w:
        w["n"] = 1
    assert wire.paths() == [OPEN_PATH, CLOSE_PATH]

    wire2 = Wire()

    async def job() -> None:
        async with _client(wire2).arecorded("y"):
            await asyncio.sleep(10)

    t = asyncio.create_task(job())
    await asyncio.sleep(0.05)
    t.cancel()
    with pytest.raises(asyncio.CancelledError):
        await t
    assert wire2.calls[-1][1]["status"] == "cancelled"


async def test_arecorded_records_an_exception() -> None:
    wire = Wire()
    with pytest.raises(RuntimeError):
        async with _client(wire).arecorded("x"):
            raise RuntimeError("down")
    assert wire.calls[-1][1]["status"] == "failed"
