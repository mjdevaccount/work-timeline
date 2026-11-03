r"""Command-line writer for callers that are not Python: `python -m work_timeline`.

Builds each request body through the same contract models as `TimelineClient`, so a shell script
(a deploy step, a cron wrapper, a CI job) sends exactly what a Python writer would.

Example:
    ```bash
    WORK_TIMELINE_API_KEY="$key" python -m work_timeline record \
        --service ci-runner --kind deploy --name api \
        --started "$started" --ended "$(date -u +%FT%TZ)" --status ok \
        --ref deploys:api --attr env=staging --base-url https://timeline.example.com/api
    ```

`open` prints the new unit's id and `close --id N` finishes it. `--dry-run` prints the body that
would be sent and makes no request.

Invariants:
    The API key is read from the environment variable named by `--key-var` (default
    `WORK_TIMELINE_API_KEY`), never from argv, where other users of the host can read it.
    Rationale: ADR-0006.

    The default variables fall back to their deprecated names (`client.read_env`); reading one
    prints a one-line warning to stderr that names the variables, never the value.

Exit codes:
    0: Sent and accepted; `open` prints the unit id.
    2: Bad input (usage, a datetime, attrs JSON, a value the contract refuses).
    3: Refused by the receiver (HTTP 400 or above).
    4: No response (timeout, connection refused).
    5: Not configured (no base URL or no API key).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import warnings
from typing import Any

from work_timeline import client as _client
from work_timeline import vocab

__all__ = ["EXIT_OK", "EXIT_REFUSED", "EXIT_UNCONFIGURED", "EXIT_UNREACHABLE", "EXIT_USAGE", "main"]

#: Exit codes, as listed in the module docstring.
EXIT_OK, EXIT_USAGE, EXIT_REFUSED, EXIT_UNREACHABLE, EXIT_UNCONFIGURED = 0, 2, 3, 4, 5


class _Probe:
    """Wraps the transport and keeps what happened, so the exit code can name the failure."""

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
        raise argparse.ArgumentTypeError(f"no timezone on {text!r}: a unit's times are instants")
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
    common.add_argument("--service", required=True, help="the writer's name; tags every unit's attrs and default ref")
    common.add_argument("--base-url", default=None, help=f"default ${_client.BASE_URL_VAR}")
    common.add_argument("--key-var", default=_client.API_KEY_VAR, help="environment variable holding the API key")
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
    sub.add_parser("open", parents=[common, row], help="open a running unit; prints its id")
    close = sub.add_parser("close", parents=[common, end], help="close a unit from `open`")
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
    """Run the command line.

    Args:
        argv: Arguments without the program name; `sys.argv[1:]` when None.

    Returns:
        One of the exit codes in the module docstring.

    Raises:
        SystemExit: With `EXIT_USAGE` on bad input, as `argparse` does.
    """
    args = _parser().parse_args(argv)
    attrs = _attrs(args)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", FutureWarning)
        base = args.base_url if args.base_url is not None else _client.read_env(_client.BASE_URL_VAR)
        key = _client.read_env(args.key_var)
    for w in caught:
        print(f"work_timeline: warning: {w.message}", file=sys.stderr)
    if args.dry_run:
        base, key = base or "http://dry-run", key or "dry-run"
    probe = _Probe(_dry if args.dry_run else _client.urllib_transport)
    tl = _client.TimelineClient(
        base, key, service=args.service, timeout_s=args.timeout, transport=probe, headers=dict(args.header)
    )
    if not tl.configured:
        missing = {"base_url": "--base-url / " + _client.BASE_URL_VAR, "api_key": args.key_var}
        return _fail(EXIT_UNCONFIGURED, "not configured: no " + ", ".join(missing[m] for m in tl.missing()))

    got: int | bool | None
    if args.cmd == "record":
        got = tl.record(
            args.name,
            kind=args.kind,
            layer=args.layer,
            ref=args.ref,
            started_at=args.started,
            ended_at=args.ended,
            status=args.status,
            error=args.error,
            attrs=attrs,
        )
    elif args.cmd == "open":
        got = tl.open(args.name, kind=args.kind, layer=args.layer, ref=args.ref, started_at=args.started, attrs=attrs)
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
            return _fail(EXIT_REFUSED, f"open answered http {probe.code} with no unit id")
        print(got)
    else:
        print(f"landed http {probe.code}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
