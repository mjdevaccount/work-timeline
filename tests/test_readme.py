"""Every Python block in the README and docs runs; a block fenced `{.python test="skip"}` is a fragment."""

from __future__ import annotations

from pathlib import Path

import pytest
from pytest_examples import CodeExample, EvalExample, find_examples

ROOT = Path(__file__).resolve().parents[1]
BLOCKS = [e for e in find_examples(ROOT / "README.md", ROOT / "docs") if e.prefix_settings().get("test") != "skip"]


def test_the_readme_example_is_collected() -> None:
    assert any(e.path.name == "README.md" for e in BLOCKS)


@pytest.mark.parametrize("example", BLOCKS, ids=str)
def test_a_markdown_python_block_runs(example: CodeExample, eval_example: EvalExample) -> None:
    eval_example.run(example)
