"""The public surface: every exported name resolves, and the version matches the distribution."""

from __future__ import annotations

import importlib
from importlib.metadata import version

import pytest

import work_timeline

MODULES = [
    "work_timeline",
    "work_timeline.vocab",
    "work_timeline.contract",
    "work_timeline.client",
    "work_timeline.cli",
]


@pytest.mark.parametrize("name", MODULES)
def test_every_exported_name_resolves(name: str) -> None:
    mod = importlib.import_module(name)
    assert mod.__all__, f"{name} exports nothing"
    missing = [n for n in mod.__all__ if not hasattr(mod, n)]
    assert missing == [], f"{name}.__all__ names {missing}, which do not exist"


def test_the_version_matches_the_distribution() -> None:
    assert work_timeline.__version__ == version("work-timeline")


def test_the_environment_defaults() -> None:
    from work_timeline import client

    assert (client.BASE_URL_VAR, client.API_KEY_VAR) == ("WORK_TIMELINE_BASE_URL", "WORK_TIMELINE_API_KEY")
