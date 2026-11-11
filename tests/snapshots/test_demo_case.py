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

from uniparser2.cli.samples import (
    SampleCase,
    read_expected,
    read_input,
    record_expected,
    run_graph,
)
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
    assert result.value == {"headings": ["First   section", "Second section"]}


def test_a_snapshot_carrying_a_non_json_constant_is_an_error(tmp_path: Path) -> None:
    """A hand-edited `expected.json` is a broken snapshot, not the value `inf`."""
    case = SampleCase(name="c", path=tmp_path / "c")
    case.path.mkdir()
    case.expected_path.write_text("Infinity", encoding="utf-8")
    value, error = read_expected(case)
    assert value is None
    assert error is not None and "non-JSON constant" in error


def test_a_product_json_cannot_express_is_reported_not_raised(tmp_path: Path) -> None:
    """`record_expected` already answered `str | None`; a non-finite product uses that path."""
    case = SampleCase(name="c", path=tmp_path / "c")
    error = record_expected(case, float("inf"))
    assert error is not None and "UP2-E1004" in error
    assert not case.expected_path.exists()


def test_a_finite_product_round_trips(tmp_path: Path) -> None:
    case = SampleCase(name="c", path=tmp_path / "c")
    assert record_expected(case, {"ratio": 1.5, "tags": ["a"]}) is None
    assert read_expected(case) == ({"ratio": 1.5, "tags": ["a"]}, None)
