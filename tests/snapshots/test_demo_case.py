"""The repository's own snapshot case (`04` §7-S4/S5, `05` §4 "Snapshots").

`samples/local/demo/` is the shipped example of the documented layout: a **story**, one case with
an ``input.txt``, and the ``expected.json`` that was frozen with ``up2 snapshot --accept``. This
module keeps the two in step -- without it, a chain could be edited and the recorded product would
keep matching nothing.

The engines are optional extras, so the case is skipped when ``selectolax`` is absent (the same
convention ``tests/ops/test_htmldom.py`` follows).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from uniparser2.cli.samples import SampleCase, read_expected, read_input, run_graph
from uniparser2.core.export import compare_products

ROOT = Path(__file__).resolve().parents[2]
CASE_ROOT = ROOT / "samples" / "local" / "demo"
STORY_PATH = CASE_ROOT / "site.json"
CASE = SampleCase(name="case-a", path=CASE_ROOT / "case-a")


def load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def test_the_demo_case_matches_its_snapshot() -> None:
    """One sample × one chain, compared structurally (`05` §4.2)."""
    pytest.importorskip("selectolax")
    graph = load(STORY_PATH)
    expected, error = read_expected(CASE)
    assert error is None
    value, error = read_input(CASE)
    assert error is None
    result = run_graph(graph, value)
    assert result.ok, result.error
    assert compare_products(expected, result.value) == []
    # The story's own product, spelled out: a change to either file lands here first.
    assert result.value == [{"headings": ["First   section", "Second section"]}]
