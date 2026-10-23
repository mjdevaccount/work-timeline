"""`python -m work_timeline`: the body is the contract's, and the exit code says which failure."""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

import pytest

import work_timeline.client as wc
from work_timeline import cli
from work_timeline.contract import CLOSE_PATH, OPEN_PATH, RECORD_PATH, WorkClose, WorkOpen, WorkRecord

REC = ["record", "--service", "edge-host", "--kind", "deploy", "--name", "service",
       "--started", "2026-10-23T14:00:00Z", "--ended", "2026-10-23T14:03:00Z", "--status", "ok"]


class _Wire:
    def __init__(self, code: int = 200, raises: Exception | None = None) -> None:
        self.code, self.raises = code, raises
        self.calls: list[tuple[str, dict[str, Any], dict[str, str]]] = []

    def __call__(self, url: str, body: bytes, headers: dict[str, str], _t: float) -> tuple[int, bytes]:
        self.calls.append((url, json.loads(body), headers))
        if self.raises:
            raise self.raises
        return self.code, b'{"id": 41}'


@pytest.fixture
def wire(monkeypatch: pytest.MonkeyPatch) -> _Wire:
    w = _Wire()
    monkeypatch.setattr(wc, "urllib_transport", w)
    monkeypatch.setenv("TRADE_DATA_API_KEY", "sekrit")
    monkeypatch.setenv("TRADE_DATA_BASE_URL", "http://td.test/api")
    return w


def test_record_posts_a_body_the_receiver_validates(wire: _Wire, capsys) -> None:
    rc = cli.main([*REC, "--ref", "ops.deploy:service", "--attr", "op=deploy", "--attr", "image=current"])
    assert rc == 0 and "landed http 200" in capsys.readouterr().out
    url, body, headers = wire.calls[0]
    assert url == "http://td.test/api" + RECORD_PATH
    WorkRecord(**body)
    assert body["kind"] == "deploy" and body["ref"] == "ops.deploy:service"
    assert body["attrs"] == {"service": "edge-host", "op": "deploy", "image": "current"}
    assert headers["X-API-Key"] == "sekrit"


def test_open_prints_the_id_and_close_sends_it(wire: _Wire, capsys) -> None:
    assert cli.main(["open", *REC[1:9]]) == 0
    assert capsys.readouterr().out.strip() == "41"
    WorkOpen(**wire.calls[0][1])
    assert wire.calls[0][0].endswith(OPEN_PATH)
    assert cli.main(["close", "--service", "edge-host", "--id", "41", "--ended",
                     "2026-10-23T14:03:00Z", "--status", "cancelled"]) == 0
    url, body, _h = wire.calls[1]
    assert url.endswith(CLOSE_PATH) and body["id"] == 41 and body["status"] == "cancelled"
    WorkClose(**body)


def test_a_header_is_added_but_cannot_replace_the_key(wire: _Wire) -> None:
    cli.main([*REC, "--header", "Host: thethinkingcap.app", "--header", "X-API-Key: forged"])
    headers = wire.calls[0][2]
    assert headers["Host"] == "thethinkingcap.app" and headers["X-API-Key"] == "sekrit"


def test_attrs_json_and_attr_merge(wire: _Wire) -> None:
    cli.main([*REC, "--attrs-json", '{"stamp": "x", "n": 3}', "--attr", "op=restore"])
    assert wire.calls[0][1]["attrs"] == {"service": "edge-host", "stamp": "x", "n": 3, "op": "restore"}


def test_an_unknown_status_lands_failed(wire: _Wire) -> None:
    """A shell caller's own word (`success`) is translated BY THE CALLER; the CLI is conservative."""
    cli.main([*REC[:-1], "success"])
    assert wire.calls[0][1]["status"] == "failed"


@pytest.mark.parametrize(("wire_kw", "want"), [({"code": 422}, cli.EXIT_REFUSED),
                                               ({"code": 503}, cli.EXIT_REFUSED),
                                               ({"raises": TimeoutError("x")}, cli.EXIT_UNREACHABLE)])
def test_refused_and_unreachable_are_different_exits(monkeypatch, capsys, wire_kw, want) -> None:
    monkeypatch.setattr(wc, "urllib_transport", _Wire(**wire_kw))
    monkeypatch.setenv("TRADE_DATA_API_KEY", "sekrit")
    assert cli.main([*REC, "--base-url", "http://td.test"]) == want
    err = capsys.readouterr().err
    assert ("REFUSED http" in err) if want == cli.EXIT_REFUSED else ("no response (TimeoutError)" in err)


def test_unconfigured_says_which_half(monkeypatch, capsys) -> None:
    monkeypatch.delenv("TRADE_DATA_API_KEY", raising=False)
    assert cli.main([*REC, "--base-url", "http://td.test"]) == cli.EXIT_UNCONFIGURED
    assert "TRADE_DATA_API_KEY" in capsys.readouterr().err


def test_the_key_is_never_printed(wire: _Wire, capsys) -> None:
    for code in (200, 422):
        wire.code = code
        cli.main(REC)
    out = capsys.readouterr()
    assert "sekrit" not in out.out + out.err


@pytest.mark.parametrize("bad", [["--started", "yesterday"], ["--started", "2026-10-23T14:00:00"],
                                 ["--attrs-json", "[1]"], ["--attrs-json", "{nope"], ["--attr", "novalue"],
                                 ["--kind", "ingest"]])
def test_bad_input_is_exit_2_and_sends_nothing(wire: _Wire, bad: list[str]) -> None:
    with pytest.raises(SystemExit) as ei:
        cli.main([*REC, *bad])
    assert ei.value.code == cli.EXIT_USAGE
    assert wire.calls == []


def test_dry_run_prints_the_body_and_needs_no_key_or_network(monkeypatch, capsys) -> None:
    def _no_network(*_a: Any) -> tuple[int, bytes]:
        raise AssertionError("dry-run touched the network")

    monkeypatch.setattr(wc, "urllib_transport", _no_network)
    monkeypatch.delenv("TRADE_DATA_API_KEY", raising=False)
    monkeypatch.delenv("TRADE_DATA_BASE_URL", raising=False)
    assert cli.main([*REC, "--dry-run", "--error", 'compose said "no"']) == 0
    body = json.loads(capsys.readouterr().out)
    assert body["error"] == 'compose said "no"'
    WorkRecord(**body)


def test_python_dash_m_runs_it() -> None:
    got = subprocess.run([sys.executable, "-m", "work_timeline", *REC, "--dry-run"],
                         capture_output=True, text=True, check=False)
    assert got.returncode == 0, got.stderr
    assert json.loads(got.stdout)["name"] == "service"
