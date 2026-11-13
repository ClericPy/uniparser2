"""Every invariant the notes declare must be executed by a case — the guard for this directory.

`up2 conformance` audits `(operator, action)` pairs and error codes. It has no notion of an
invariant, so the previous failure mode went unnoticed: `01`/`02`/`03` described `type` as a
chain-tail JSON validator, each operator's own tests agreed with that sentence, and every gate
stayed green while the engine did the wrong thing.

This module is the missing link: a declared invariant with no `INVARIANT_CASES` entry is a red gate,
so "the doc says X" and "a test executes X" cannot drift apart silently. The ids come from the
notes themselves — `00` §2's `N1`–`N8` contract table and `01` §1.1's `I1`–`I8` — so the audit
covers exactly what is declared, where it is declared.

Adding an invariant to `00` §2 or `01` §1.1 means adding a case reference here; writing the
reference is a one-line edit in the table below, and the referenced case must exist in this
directory.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

INVARIANT_CASES: dict[str, str] = {
    # invariant id (as written in 00 §2 / 01 §1.1) -> the test function that executes it
    "I1": "test_core_imports_the_standard_library_only",
    "I2": "test_dependencies_point_downward_only",
    "I5": "test_no_operator_performs_io_on_the_evaluate_path",
    "N2": "test_a_chain_round_trips_whatever_an_operator_adds",
    "N4": "test_every_action_answers_a_value_or_a_failure_never_a_third_state",
    "N5": "test_the_exit_hands_back_what_the_run_produced",
    "N8": "test_the_kernel_is_fully_synchronous",
}
"""A declared invariant is executed here. Keys are the ids `00` §2 and `01` §1.1 declare."""

# Invariants whose guarantee is structural (a compile-time table, a module boundary) and whose
# enforcement is a different gate; listed so the audit is explicit rather than accidental.
ENFORCED_ELSEWHERE: dict[str, str] = {
    "I3": "no export check: the product is the value, asserted by `N5`'s case below",
    "I4": "`compile_field` returns a standalone `CompiledField`, never a `str` subclass or the "
    "chain dict: `tests/compile`",
    "I6": "control flow is a stage: `each` / the `try` directive are registry stages, `tests/ops`",
    "I7": "lazy engine imports: the `find_spec` guard in `tests/core/test_core_edges.py`",
    "I8": "only linted chains reach the runtime: `tests/compile`",
    "N1": "no side effects / no global state: `I5` above, plus `tests/core` scope isolation",
    "N3": "a bad chain fails at compile time: the whole `tests/compile` directory",
    "N6": "no code capability inside a rule: the sandbox gate (`tests/ops/test_code_gate.py`) and "
    "the dependency-gated registry (`tests/ops/test_registry.py`)",
    "N7": "callable nodes and no DAG scheduling: the acyclic-call-graph compile cases "
    "(`UP2-E1016`/`E1017`) in `tests/chains/test_story.py`",
}


def _notes() -> list[Path]:
    """The notes that declare invariant ids: `00` (the N1–N8 contract table), `01` (I1–I8)."""
    root = Path(__file__).resolve().parents[2] / "docs" / "specs"
    return [root / "000-overview.md", root / "001-architecture-and-value-model.md"]


def _declared_invariants() -> set[str]:
    """The ids the design notes declare, read from their tables rather than written down twice."""
    from uniparser2.core.invariants import parse_declared

    declared: set[str] = set()
    for note in _notes():
        declared |= parse_declared(note.read_text(encoding="utf-8"))
    return declared


def _cases_in_this_directory() -> set[str]:
    found: set[str] = set()
    for path in Path(__file__).resolve().parent.glob("test_*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                found.add(node.name)
    return found


def test_every_declared_invariant_is_accounted_for() -> None:
    declared = _declared_invariants()
    assert declared, "the notes declare no invariants; the parser or the layout changed"
    uncovered = sorted(declared - set(INVARIANT_CASES) - set(ENFORCED_ELSEWHERE))
    assert not uncovered, (
        f"invariant(s) {uncovered} are declared in 00/01 but no case executes them: add a case "
        "here and reference it in INVARIANT_CASES, or record where it is enforced"
    )


def test_no_case_references_an_invariant_that_does_not_exist() -> None:
    declared = _declared_invariants()
    stale = sorted((set(INVARIANT_CASES) | set(ENFORCED_ELSEWHERE)) - declared)
    assert not stale, f"case(s) reference invariant id(s) the notes no longer declare: {stale}"


def test_every_referenced_case_exists() -> None:
    cases = _cases_in_this_directory()
    missing = sorted(set(INVARIANT_CASES.values()) - cases)
    assert not missing, f"INVARIANT_CASES names case(s) that do not exist here: {missing}"


def test_every_live_code_has_a_throw_site() -> None:
    """A code in ``CODES`` is a promise that the engine can emit it; a throw site is the proof.

    ``conformance`` checks codes against **tests**, not against the code. Without this, a number
    could sit in ``CODES`` that nothing raises -- and the reverse, a retired number silently being
    emitted again, is what the next case guards.
    """
    from uniparser2.core.errors import CODES

    thrown = _codes_in_sources()
    never = sorted(set(CODES) - thrown)
    assert not never, f"code(s) declared in CODES that no source line raises: {never}"


def test_no_retired_number_is_still_thrown() -> None:
    """`01` §4.3: a code is **stable**, so a retired number is never reused and never emitted."""
    from uniparser2.core.errors import RETIRED

    thrown = _codes_in_sources()
    reused = sorted(set(RETIRED) & thrown)
    assert not reused, f"retired number(s) still raised by the engine: {reused}"


def test_a_code_is_live_or_retired_never_both() -> None:
    from uniparser2.core.errors import CODES, RETIRED

    both = sorted(set(CODES) & set(RETIRED))
    assert not both, f"code(s) in both CODES and RETIRED: {both}"


def test_every_retired_number_says_why() -> None:
    from uniparser2.core.errors import RETIRED

    silent = sorted(number for number, reason in RETIRED.items() if len(reason.strip()) < 20)
    assert not silent, f"retired number(s) without a reason: {silent}"


def _codes_in_sources() -> set[str]:
    """Every code literal written in ``src/``, the tables aside."""
    import re

    root = Path(__file__).resolve().parents[2] / "src"
    pattern = re.compile(r"UP2-E\d{4}")
    found: set[str] = set()
    for path in root.rglob("*.py"):
        if path.name == "errors.py":
            continue  # the tables themselves are not throw sites
        found.update(pattern.findall(path.read_text(encoding="utf-8")))
    return found


@pytest.mark.parametrize("invariant", sorted(INVARIANT_CASES))
def test_the_declared_invariant_has_a_reason_it_needs_this_layer(invariant: str) -> None:
    """The case must belong to this directory, not to an operator's own file.

    An invariant that one operator's tests could cover is not an invariant — it is that operator's
    behaviour. Keeping the cross-operator ones here is what made the `type` defect visible.
    """
    assert INVARIANT_CASES[invariant].startswith("test_")
