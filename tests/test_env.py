"""Environment defaults: the current names win, the deprecated names still work and warn once."""

from __future__ import annotations

import warnings
from typing import Any

import pytest

import work_timeline.client as wc
from work_timeline import TimelineClient, cli

OLD_BASE, OLD_KEY = wc.LEGACY_ENV_VARS[wc.BASE_URL_VAR], wc.LEGACY_ENV_VARS[wc.API_KEY_VAR]
REC = [
    "record",
    "--service",
    "ci-runner",
    "--name",
    "api",
    "--started",
    "2030-01-01T12:00:00Z",
    "--ended",
    "2030-01-01T12:03:00Z",
    "--status",
    "ok",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (wc.BASE_URL_VAR, wc.API_KEY_VAR, OLD_BASE, OLD_KEY):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(wc, "_warned", set())


def test_the_current_name_wins_without_a_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(wc.API_KEY_VAR, "new")
    monkeypatch.setenv(OLD_KEY, "old")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert wc.read_env(wc.API_KEY_VAR) == "new"


def test_a_deprecated_name_is_read_and_warns_once(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(OLD_KEY, "old-secret")
    with pytest.warns(FutureWarning, match=f"{OLD_KEY} is deprecated.*set {wc.API_KEY_VAR}") as got:
        assert wc.read_env(wc.API_KEY_VAR) == "old-secret"
        assert wc.read_env(wc.API_KEY_VAR) == "old-secret"
    assert len(got) == 1 and "old-secret" not in str(got[0].message)


def test_an_unset_variable_reads_empty_and_does_not_warn() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert wc.read_env(wc.BASE_URL_VAR) == "" and wc.read_env("SOME_OTHER_VAR") == ""


def test_from_env_falls_back_to_the_deprecated_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(OLD_BASE, "http://timeline.test")
    monkeypatch.setenv(OLD_KEY, "k")
    with pytest.warns(FutureWarning):
        assert TimelineClient.from_env(service="ci-runner").configured


def test_from_env_with_explicit_names_reads_only_those(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_URL", "http://timeline.test")
    monkeypatch.setenv("MY_KEY", "k")
    assert TimelineClient.from_env(service="s", base_var="MY_URL", key_var="MY_KEY").configured


def test_the_cli_takes_the_deprecated_key_and_says_so_once(monkeypatch, capsys) -> None:
    sent: list[Any] = []
    monkeypatch.setattr(wc, "urllib_transport", lambda *a: sent.append(a) or (200, b"{}"))
    monkeypatch.setenv(OLD_KEY, "old-secret")
    assert cli.main([*REC, "--base-url", "http://timeline.test"]) == cli.EXIT_OK
    err = capsys.readouterr().err
    assert err.count("work_timeline: warning:") == 1 and OLD_KEY in err and "old-secret" not in err
    assert sent[0][2]["X-API-Key"] == "old-secret"


def test_an_explicit_key_var_has_no_fallback(monkeypatch, capsys) -> None:
    monkeypatch.setenv(OLD_KEY, "old-secret")
    assert cli.main([*REC, "--base-url", "http://timeline.test", "--key-var", "MY_KEY"]) == cli.EXIT_UNCONFIGURED
    assert "MY_KEY" in capsys.readouterr().err
