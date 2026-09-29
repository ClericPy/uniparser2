"""Conformance audit (design doc 05 §4.1).

Two things:
1. **The repository's current state must be clean** -- the declarations ``scan_tests`` finds agree
   exactly with the registry and the code table;
2. the set arithmetic of ``core.conformance.check`` is itself correct (missing entries and orphan
   entries are both identified).
"""

from __future__ import annotations

import json
from pathlib import Path

from uniparser2.cli.conformance import scan_tests
from uniparser2.core import registry
from uniparser2.core.conformance import check
from uniparser2.core.errors import CODES

TESTS_ROOT = Path(__file__).resolve().parents[1]
# A deliberately nonexistent code. It must be built rather than written as a literal: the
# conformance scan reads a `UP2-E` + 4 digits occurrence in test source as the declaration
# "this code is covered", and a literal would pollute the repository-level audit result.
UNKNOWN_CODE = "UP2-E" + "9999"


def test_repository_conformance_is_clean() -> None:
    pairs, codes = scan_tests(TESTS_ROOT)
    report = check(covered_pairs=pairs, covered_codes=codes)
    assert report.ok, report.render()


def test_scan_finds_decorator_and_constant_declarations() -> None:
    pairs, _ = scan_tests(TESTS_ROOT)
    assert ("re", "search") in pairs  # decorator form
    assert ("py", "sha256") in pairs  # module-level COVERS_PAIRS form
    assert ("udf", registry.DYNAMIC_ACTION_MARK) in pairs  # the * declaration of a dynamic space


def test_check_reports_missing_pairs() -> None:
    report = check(
        covered_pairs=[("py", "strip")],
        covered_codes=list(CODES),
        declared_pairs=[("py", "strip"), ("py", "join")],
        declared_codes=list(CODES),
    )
    assert not report.ok
    assert report.missing_pairs == (("py", "join"),)


def test_check_reports_orphan_pairs() -> None:
    report = check(
        covered_pairs=[("py", "strip"), ("gone", "x")],
        covered_codes=list(CODES),
        declared_pairs=[("py", "strip")],
        declared_codes=list(CODES),
    )
    assert report.orphan_pairs == (("gone", "x"),)


def test_check_reports_missing_codes() -> None:
    report = check(
        covered_pairs=[],
        covered_codes=["UP2-E1001"],
        declared_pairs=[],
        declared_codes=["UP2-E1001", "UP2-E2002"],
    )
    assert report.missing_codes == ("UP2-E2002",)


def test_check_reports_orphan_codes() -> None:
    report = check(
        covered_pairs=[],
        covered_codes=["UP2-E1001", UNKNOWN_CODE],
        declared_pairs=[],
        declared_codes=["UP2-E1001"],
    )
    assert report.orphan_codes == (UNKNOWN_CODE,)


def test_report_serialises() -> None:
    pairs, codes = scan_tests(TESTS_ROOT)
    payload = check(covered_pairs=pairs, covered_codes=codes).to_dict()
    assert json.loads(json.dumps(payload))["ok"] is True


def test_declared_pairs_match_registry_at_check_time() -> None:
    """The audit compares against the registry itself, not the docs: no second source of truth."""
    pairs, _ = scan_tests(TESTS_ROOT)
    declared = {pair for pair in pairs if pair[0] in registry.canonical_names()}
    assert declared == set(registry.declared_pairs())
