"""`python -m work_timeline` -- the remote writer for callers that are not Python (a deploy script).

A shell writer that builds the JSON itself re-types the contract: its own escaping, its own field
names, its own status vocabulary, and a body the receiver may refuse with nobody looking. This
command builds the body through the SAME models the receiver validates with, so a shell caller
inherits the contract instead of copying it.

    TRADE_DATA_API_KEY=... python -m work_timeline record --service edge-host --kind deploy \\
        --name service --started 2026-10-23T14:00:00Z --ended 2026-10-23T14:03:00Z --status ok \\
        --ref ops.deploy:service --attr op=deploy --base-url http://127.0.0.1:8088/api

THE KEY NEVER RIDES ARGV (host `ps` shows argv to every user): it is read from the environment
variable `--key-var` names, default TRADE_DATA_API_KEY.

`--dry-run` prints the exact body that would be sent and touches no network, so a caller's own
test can assert on what the receiver would get.

EXIT CODES are the caller's contract. The work being observed must never fail because of them --
a caller logs the line and carries on -- but they keep "refused" and "unreachable" apart, which a
fire-and-forget POST cannot:
  0  landed (open prints the new row's id)       3  REFUSED by the receiver (http 4xx/5xx)
  2  bad input: usage, a datetime, attrs JSON    4  no response (timeout, refused connection)
  5  not configured: no base URL or no key
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from typing import Any

from work_timeline import client as _client
from work_timeline import vocab

EXIT_OK, EXIT_USAGE, EXIT_REFUSED, EXIT_UNREACHABLE, EXIT_UNCONFIGURED = 0, 2, 3, 4, 5


class _Probe:
    """Wraps the transport to remember what happened, so the exit code can say which failure."""

    def __init__(self, inner: _client.Transport) -> None:
        self.inner = inner
        self.code: int | None = None
        self.exc: BaseException | None = None
        self.body: bytes | None = None

    def __call__(self, url: str, body: bytes, headers: dict[str, str], timeout_s: float) -> tuple[int, bytes]:
        self.body = body
        try:
            self.code, raw = self.inner(url, body, headers, timeout_s)
        except Exception as exc:
            self.exc = exc
            raise
        return self.code, raw


def _dry(_url: str, body: bytes, _headers: dict[str, str], _timeout_s: float) -> tuple[int, bytes]:
    return 200, b'{"id": 0}'


def _when(text: str) -> dt.datetime:
    try:
        got = dt.datetime.fromisoformat(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not an ISO 8601 datetime: {text!r}") from exc
    if got.tzinfo is None:
        raise argparse.ArgumentTypeError(f"no timezone on {text!r}: the timeline stores instants")
    return got


def _header(text: str) -> tuple[str, str]:
    name, sep, value = text.partition(":")
    if not sep or not name.strip():
        raise argparse.ArgumentTypeError(f"a header is 'Name: value', got {text!r}")
    return name.strip(), value.strip()


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m work_timeline", description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--service", required=True, help="tags every row's attrs and default ref")
    common.add_argument("--base-url", default=None, help=f"default ${_client.BASE_URL_VAR}")
    common.add_argument("--key-var", default=_client.API_KEY_VAR, help="env var holding the key")
    common.add_argument("--header", type=_header, action="append", default=[], help="'Name: value'")
    common.add_argument("--timeout", type=float, default=_client.DEFAULT_TIMEOUT_S)
    common.add_argument("--attr", action="append", default=[], metavar="K=V", help="a string attr")
    common.add_argument("--attrs-json", default=None, help="a JSON object of attrs")
    common.add_argument("--dry-run", action="store_true", help="print the body; send nothing")
    row = argparse.ArgumentParser(add_help=False)
    row.add_argument("--name", required=True)
    row.add_argument("--kind", default="job", choices=sorted(vocab.KINDS))
    row.add_argument("--layer", default="process", choices=vocab.LAYERS)
    row.add_argument("--ref", default=None, help="default <service>:<name>")
    row.add_argument("--started", type=_when, required=True)
    end = argparse.ArgumentParser(add_help=False)
    end.add_argument("--ended", type=_when, required=True)
    end.add_argument("--status", required=True, help="ok|failed|cancelled; anything else -> failed")
    end.add_argument("--error", default=None)
    sub.add_parser("record", parents=[common, row, end], help="one finished unit")
    sub.add_parser("open", parents=[common, row], help="open a running row; prints its id")
    close = sub.add_parser("close", parents=[common, end], help="close a row from `open`")
    close.add_argument("--id", type=int, required=True)
    return p


def _attrs(args: argparse.Namespace) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if args.attrs_json:
        try:
            got = json.loads(args.attrs_json)
        except ValueError as exc:
            raise SystemExit(_fail(EXIT_USAGE, f"--attrs-json is not JSON: {exc}")) from exc
        if not isinstance(got, dict):
            raise SystemExit(_fail(EXIT_USAGE, "--attrs-json must be a JSON object"))
        out.update(got)
    for kv in args.attr:
        k, sep, v = kv.partition("=")
        if not sep or not k:
            raise SystemExit(_fail(EXIT_USAGE, f"--attr is K=V, got {kv!r}"))
        out[k] = v
    return out


def _fail(code: int, msg: str) -> int:
    print(f"work_timeline: {msg}", file=sys.stderr)
    return code


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    attrs = _attrs(args)
    base = args.base_url if args.base_url is not None else os.environ.get(_client.BASE_URL_VAR, "")
    key = os.environ.get(args.key_var, "")
    if args.dry_run:
        base, key = base or "http://dry-run", key or "dry-run"
    probe = _Probe(_dry if args.dry_run else _client.urllib_transport)
    tl = _client.TimelineClient(base, key, service=args.service, timeout_s=args.timeout,
                                transport=probe, headers=dict(args.header))
    if not tl.configured:
        missing = {"base_url": "--base-url / " + _client.BASE_URL_VAR, "api_key": args.key_var}
        return _fail(EXIT_UNCONFIGURED, "not configured: no " + ", ".join(missing[m] for m in tl.missing()))

    got: int | bool | None
    if args.cmd == "record":
        got = tl.record(args.name, kind=args.kind, layer=args.layer, ref=args.ref, started_at=args.started,
                        ended_at=args.ended, status=args.status, error=args.error, attrs=attrs)
    elif args.cmd == "open":
        got = tl.open(args.name, kind=args.kind, layer=args.layer, ref=args.ref, started_at=args.started,
                      attrs=attrs)
    else:
        got = tl.close(args.id, ended_at=args.ended, status=args.status, error=args.error, attrs=attrs)

    if probe.body is None:
        return _fail(EXIT_USAGE, "the body did not build (a value the contract refuses)")
    if args.dry_run:
        print(probe.body.decode())
        return EXIT_OK
    if probe.exc is not None:
        return _fail(EXIT_UNREACHABLE, f"no response ({type(probe.exc).__name__})")
    if probe.code is not None and probe.code >= 400:
        return _fail(EXIT_REFUSED, f"REFUSED http {probe.code}")
    if args.cmd == "open":
        if got is None:
            return _fail(EXIT_REFUSED, f"open answered http {probe.code} with no row id")
        print(got)
    else:
        print(f"landed http {probe.code}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
