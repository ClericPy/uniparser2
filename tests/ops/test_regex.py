"""``re`` operator behaviour assertions and the ReDoS static check (design doc 02 §6.3)."""

from __future__ import annotations

from typing import Any

import pytest

from uniparser2 import Failed, Ok, Outcome, Up2Error, compile_field, eval_field


def run(chain: Any, value: Any) -> Outcome:
    compiled = compile_field(chain)
    return eval_field(compiled, value)


def compile_error(chain: Any) -> str:
    with pytest.raises(Up2Error) as info:
        compile_field(chain)
    return info.value.diagnostic.code


@pytest.mark.covers("re", "search")
def test_match_returns_group_zero_or_empty() -> None:
    assert run([["re", "search", r"\d+"]], "a12b") == Ok("12")
    assert run([["re", "search", r"\d+"]], "abc") == Ok("")


@pytest.mark.covers("re", "search")
def test_group_by_index_and_by_name() -> None:
    assert run([["re", "search", [r"(\d+)-(\d+)", 2]]], "1-2") == Ok("2")
    assert run([["re", "search", [r"(?P<y>\d{4})", "y"]]], "x2026") == Ok("2026")


@pytest.mark.covers("re", "search")
def test_group_unmatched_yields_empty() -> None:
    assert run([["re", "search", [r"(\d+)", 1]]], "abc") == Ok("")


@pytest.mark.covers("re", "sub")
def test_sub_replaces_every_match() -> None:
    assert run([["re", "sub", [r"(\d{4})-(\d{2})", r"\2/\1"]]], "2026-09 x 2027-01") == Ok(
        "09/2026 x 01/2027"
    )
    assert run([["re", "sub", ["x", "y"]]], "abc") == Ok("abc")
    assert compile_error([["re", "sub", ["(a)", r"\2"]]]) == "UP2-E1005"


@pytest.mark.covers("re", "findall")
def test_all_returns_findall_results() -> None:
    assert run([["re", "findall", r"\d+"]], "a1b22") == Ok(["1", "22"])
    assert run([["re", "findall", r"\d+"]], "abc") == Ok([])


def test_non_text_input_is_type_failure() -> None:
    outcome = run([["re", "search", r"\d+"]], 12)
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2002"


def test_bad_regex_is_schema_error() -> None:
    assert compile_error([["re", "search", "("]]) == "UP2-E1005"


def test_group_out_of_range_is_schema_error() -> None:
    assert compile_error([["re", "search", ["(a)", 3]]]) == "UP2-E1005"


def test_unknown_group_name_is_schema_error() -> None:
    assert compile_error([["re", "search", ["(a)", "nope"]]]) == "UP2-E1005"


def test_nested_quantifier_is_rejected() -> None:
    assert compile_error([["re", "search", "(a+)+$"]]) == "UP2-E1013"
    assert compile_error([["re", "search", r"(\w*)*!"]]) == "UP2-E1013"


def test_legit_quantified_group_is_not_rejected() -> None:
    """`(\\d+\\.)+` is a legal spelling used by plenty of real rules and must not be killed."""
    assert run([["re", "search", r"(\d+\.)+"]], "1.2.3.") == Ok("1.2.3.")


def test_missing_pattern_is_schema_error() -> None:
    """The arity must write all 3 slots; slot 3 ``None`` means "no parameter passed".

    That leaves the required pattern missing.
    """
    assert compile_error([["re", "search", None]]) == "UP2-E1005"


@pytest.mark.covers("re", "findall")
def test_findall_encodes_tuples_as_arrays() -> None:
    """Python's ``findall`` answers tuples for two or more groups; the value domain has no tuple."""
    assert run([["re", "findall", r"(\d+)-(\d+)"]], "1-2 3-4") == Ok([["1", "2"], ["3", "4"]])


@pytest.mark.covers("re", "search")
def test_a_numeric_string_group_runs_as_an_index() -> None:
    """The compiler accepts "1" as an index; the runtime must not re-read it as a group name."""
    assert run([["re", "search", [r"(\d+)-(\d+)", "2"]]], "1-2") == Ok("2")
