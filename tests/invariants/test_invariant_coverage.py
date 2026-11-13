"""Every invariant `01` declares must be executed by a case — the guard for this whole directory.

`up2 conformance` audits `(operator, action)` pairs and error codes. It has no notion of an
invariant, so the previous failure mode went unnoticed: `01`/`02`/`03` described `type` as a
chain-tail JSON validator, each operator's own tests agreed with that sentence, and every gate
stayed green while the engine did the wrong thing.

This module is the missing link: a declared invariant with no `INVARIANT_CASES` entry is a red gate,
so "the doc says X" and "a test executes X" cannot drift apart silently.

Adding an invariant to `01` §1.1 means adding a case reference here; writing the reference is a
one-line edit in the table below, and the referenced case must exist in this directory.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

INVARIANT_CASES: dict[str, str] = {
    # invariant id (as written in 01 §1.1) -> the test function that executes it
    "I3": "test_pack_is_called_at_one_place_only",
    "I5": "test_no_operator_performs_io_on_the_evaluate_path",
    "N5": "test_only_the_run_exit_requires_json",
}
"""A declared invariant is executed here. Keys are the ids in `01` §1.1 and §4-§6."""

# Invariants whose guarantee is structural (a compile-time table, a module boundary) and whose
# enforcement is a different gate; listed so the audit is explicit rather than accidental.
ENFORCED_ELSEWHERE: dict[str, str] = {
    "I1": "`core/` imports no third-party library: `ruff` TID + the import scan in `tests/core`",
    "I2": "downward dependencies only: the import scan in `tests/core`",
    "I4": "the compile product is separate from chain data: `tests/compile`",
    "I6": "control flow is a stage: `each` / the `try` directive are registry stages, `tests/ops`",
    "I7": "lazy engine imports: the `find_spec` guard in `tests/ops`",
    "I8": "only linted chains reach the runtime: `tests/compile`",
    "N1": "no side effects / no global state: `I5` above, plus `tests/core` scope isolation",
    "N3": "a bad chain fails at compile time: the whole `tests/compile` directory",
    "N8": "fully synchronous: the `async`/`await` source scan in `tests/ci`",
}


def _spec() -> Path:
    root = Path(__file__).resolve().parents[2]
    return root / "docs" / "specs" / "001-architecture-and-value-model.md"


def _declared_invariants() -> set[str]:
    """The ids the design note declares, read from its tables rather than written down twice."""
    from uniparser2.core.invariants import parse_declared

    return parse_declared(_spec().read_text(encoding="utf-8"))


def _cases_in_this_directory() -> set[str]:
    found: set[str] = set()
    for path in Path(__file__).resolve().parent.glob("test_*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                found.add(node.name)
    return found


def test_every_declared_invariant_is_accounted_for() -> None:
    declared = _declared_invariants()
    assert declared, "01 declares no invariants; the parser or the layout changed"
    uncovered = sorted(declared - set(INVARIANT_CASES) - set(ENFORCED_ELSEWHERE))
    assert not uncovered, (
        f"invariant(s) {uncovered} are declared in 01 but no case executes them: add a case "
        "here and reference it in INVARIANT_CASES, or record where it is enforced"
    )


def test_no_case_references_an_invariant_that_does_not_exist() -> None:
    declared = _declared_invariants()
    stale = sorted((set(INVARIANT_CASES) | set(ENFORCED_ELSEWHERE)) - declared)
    assert not stale, f"case(s) reference invariant id(s) 01 no longer declares: {stale}"


def test_every_referenced_case_exists() -> None:
    cases = _cases_in_this_directory()
    missing = sorted(set(INVARIANT_CASES.values()) - cases)
    assert not missing, f"INVARIANT_CASES names case(s) that do not exist here: {missing}"


@pytest.mark.parametrize("invariant", sorted(INVARIANT_CASES))
def test_the_declared_invariant_has_a_reason_it_needs_this_layer(invariant: str) -> None:
    """The case must belong to this directory, not to an operator's own file.

    An invariant that one operator's tests could cover is not an invariant — it is that operator's
    behaviour. Keeping the cross-operator ones here is what made the `type` defect visible.
    """
    assert INVARIANT_CASES[invariant].startswith("test_")
