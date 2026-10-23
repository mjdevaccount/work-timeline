from __future__ import annotations

import asyncio
import datetime as dt

import pytest
from pydantic import ValidationError

from work_timeline import contract, vocab


def test_terminal_is_derived_from_statuses() -> None:
    assert vocab.TERMINAL == ("ok", "failed", "cancelled")
    assert vocab.RUNNING in vocab.STATUSES and vocab.RUNNING not in vocab.TERMINAL


@pytest.mark.parametrize(("exc", "http", "want"), [
    (None, None, "ok"), (None, 200, "ok"), (None, 399, "ok"), (None, 400, "failed"), (None, 503, "failed"),
    (ValueError(), None, "failed"), (ValueError(), 200, "failed"),
    (asyncio.CancelledError(), None, "cancelled"), (KeyboardInterrupt(), 500, "cancelled"),
    (SystemExit(1), None, "cancelled"),
])
def test_status_for(exc: BaseException | None, http: int | None, want: str) -> None:
    assert vocab.status_for(exc, http) == want


@pytest.mark.parametrize(("got", "want"), [("ok", "ok"), ("cancelled", "cancelled"), ("success", "failed"),
                                           ("running", "failed"), ("", "failed")])
def test_terminal_coercion_is_conservative(got: str, want: str) -> None:
    assert vocab.terminal(got) == want


def test_error_text_is_capped() -> None:
    assert vocab.error_text(ValueError("x" * 900)).startswith("ValueError: x")
    assert len(vocab.error_text(ValueError("x" * 900))) == vocab.ERROR_MAX


def test_the_receiver_model_keeps_the_error_and_refuses_an_uncapped_one() -> None:
    t = dt.datetime(2026, 10, 23, tzinfo=dt.UTC)
    assert contract.WorkRecord(kind="job", name="x", started_at=t, ended_at=t, error="why").error == "why"
    with pytest.raises(ValidationError):
        contract.WorkRecord(kind="job", name="x", started_at=t, ended_at=t, error="x" * (vocab.ERROR_MAX + 1))


def test_the_record_path_is_not_under_admin_run() -> None:
    assert not contract.RECORD_PATH.startswith("/admin/run/")
