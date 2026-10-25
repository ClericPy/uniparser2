"""The report tool's own rendering rules — the contract a reader of the catalogue relies on.

``tools/demo_report.py`` renders the committed catalogue, so its rules are worth pinning the way
any behaviour is: an input is never elided, a selector case states what it matched, the scope a
case depends on is visible, and "the shared sample" is only claimed when it is true. The freshness
test in ``test_catalogue.py`` keeps the file in sync with the tool; these keep the tool honest.

The module is self-contained on purpose (no test imports another test here): the tool is loaded by
path for the same reason ``test_catalogue.py`` documents, and the skip condition is derived from the
registry the same way.
"""

from __future__ import annotations

import dataclasses
import html
import importlib.util
import sys
from collections.abc import Iterable
from pathlib import Path
from types import ModuleType

import pytest

from uniparser2.core import registry

_ROOT = Path(__file__).resolve().parents[2]

_SELECTOR_OPS = frozenset({"css", "css1", "xpath"})


def _load_report_tool() -> ModuleType:
    """Import ``tools/demo_report.py`` by path (it lives outside the package on purpose)."""
    spec = importlib.util.spec_from_file_location(
        "demo_report_rendering", _ROOT / "tools" / "demo_report.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["demo_report_rendering"] = module
    spec.loader.exec_module(module)
    return module


demo_report = _load_report_tool()


def _missing_engines(names: Iterable[str]) -> tuple[str, ...]:
    return tuple(name for name in names if importlib.util.find_spec(name) is None)


def _required_engines() -> tuple[str, ...]:
    names: set[str] = set()
    for item in registry.report():
        names.update(item.requires)
        for action in item.actions:
            names.update(action.requires)
    return tuple(sorted(names))


_MISSING = _missing_engines(_required_engines())

pytestmark = pytest.mark.skipif(
    bool(_MISSING),
    reason=f"the catalogue needs every optional engine; missing: {', '.join(_MISSING)}",
)


def test_the_css_sample_keeps_the_node_the_selectors_target() -> None:
    """The section sample is whole and open: the selector's own target must be inside it."""
    page = demo_report.build_html()
    block = html.unescape(page[page.find('id="input-css"') :].split("</details>")[0])
    assert '<details class="doc" id="input-css" open>' in page
    assert 'class="article-title"' in block
    assert "</html>" in block
    assert "…" not in block


def test_no_input_is_ever_elided() -> None:
    """Inputs are evidence, not noise: whatever the value, nothing of it is cut away."""
    for case in demo_report.coverage_cases():
        assert "…" not in demo_report._render_input(case.value)


def test_every_selector_case_states_what_it_matched() -> None:
    for case in demo_report.coverage_cases():
        if case.op in _SELECTOR_OPS:
            assert demo_report._matched_text(demo_report._run(case)), case.action


def test_a_selector_that_matches_partly_says_so() -> None:
    """``script,style`` over a sample with no ``<style>``: one node, visibly not two."""
    case = next(
        case
        for case in demo_report.coverage_cases()
        if case.op == "css" and case.action == "remove"
    )
    assert demo_report._matched_text(demo_report._run(case)) == "1 node · script"


def test_the_scope_a_case_reads_is_visible() -> None:
    """``ctx.get`` reads the scope, so the scope — not ``None`` — is the input the reader sees."""
    md = demo_report.build_md()
    assert "scope: `locals {'k': 'local value'}`" in md
    assert "input: not used — the value is read from the scope path" in md


def test_a_case_marked_ignores_input_really_does() -> None:
    """The claim is verified, not trusted: a different upstream must not move the outcome."""
    checked = 0
    for case in demo_report.coverage_cases():
        if not case.ignores_input:
            continue
        checked += 1
        base = demo_report._run(case)
        other = demo_report._run(dataclasses.replace(case, value=42))
        assert base.state == other.state, case.action
        assert base.outcome_repr == other.outcome_repr, case.action
    assert checked >= 4


def test_a_shared_sample_is_only_claimed_when_true() -> None:
    for item, cases, _, _ in demo_report._collect().sections():
        shared = demo_report._shared_input(cases)
        if not shared:
            continue
        assert len({repr(ran.case.value) for ran in cases}) == 1, item.name
        assert not any(ran.case.ignores_input for ran in cases), item.name
        assert len(shared) >= demo_report._SAMPLE_THRESHOLD, item.name


def test_the_markdown_no_longer_claims_one_input_for_a_section_of_many() -> None:
    """`py`'s 42 actions have 42 different inputs; the section header must not say otherwise."""
    section = demo_report.build_md().split("## `py`")[1].split("## `xpath`")[0]
    assert "Shared input" not in section
