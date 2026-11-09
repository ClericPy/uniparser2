"""The predicate actions: comparison, membership, selection and existence.

The action names are Python's own (`==`, `!=`, `<`, `<=`, `>`, `>=`, `in`, `or`, `and`), so a chain
reads like the expression it means. The order follows the delta spec: one-stage comparisons, `in`,
the selection actions, and existence on the selector family — `exists` in particular never leans on
what a missing value settles to, which is what `nodes` does.
"""

from __future__ import annotations

from typing import Any

import pytest

from uniparser2 import Failed, Ok, Up2Error, compile_field, eval_field

HTML = '<ul class="list"><li>x</li></ul>'


def run(chain: Any, value: Any) -> Any:
    return eval_field(compile_field(chain), value)


# ---------------------------------------------------------------- comparison


@pytest.mark.covers("py", "==")
def test_equality_answers_a_boolean() -> None:
    assert run([["py", "==", 200]], 200) == Ok(True)
    assert run([["py", "==", 200]], "200") == Ok(False)  # no type coercion


@pytest.mark.covers("py", "!=")
def test_not_equal_is_the_negation_of_equality() -> None:
    assert run([["py", "!=", 200]], "200") == Ok(True)


@pytest.mark.covers("py", "<")
def test_less_than_compares_like_types() -> None:
    assert run([["py", "<", 10]], 5) == Ok(True)
    assert run([["py", "<", "b"]], "a") == Ok(True)


@pytest.mark.covers("py", "<")
def test_less_than_rejects_an_incomparable_pair() -> None:
    outcome = run([["py", "<", 10]], "abc")
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2002"
    assert "str" in outcome.reason and "int" in outcome.reason


@pytest.mark.covers("py", "<=")
def test_less_or_equal() -> None:
    assert run([["py", "<=", 5]], 5) == Ok(True)


@pytest.mark.covers("py", ">")
def test_greater_than() -> None:
    assert run([["py", ">", 5]], 6) == Ok(True)


@pytest.mark.covers("py", ">=")
def test_greater_or_equal() -> None:
    assert run([["py", ">=", "b"]], "c") == Ok(True)


@pytest.mark.covers("py", "==")
def test_a_reference_is_accepted_as_the_second_operand() -> None:
    chain = [["py", "const", 5], ["ctx", "set", "locals._n"], ["py", "==", "$locals._n"]]
    assert run(chain, 5) == Ok(True)


@pytest.mark.covers("py", "==")
def test_equality_compares_containers_deeply() -> None:
    assert run([["py", "==", {"a": [1, 2]}]], {"a": [1, 2]}) == Ok(True)
    assert run([["py", "==", []]], []) == Ok(True)


@pytest.mark.covers("py", "==")
def test_equality_is_pythons_own_so_a_boolean_equals_its_number() -> None:
    """The documented asymmetry: `==` follows Python, the orderings reject a boolean."""
    assert run([["py", "==", 1]], True) == Ok(True)
    assert run([["py", "==", 0]], False) == Ok(True)
    assert run([["py", "in", [1]]], True) == Ok(True)


@pytest.mark.covers("py", "<")
def test_ordering_rejects_a_boolean_operand() -> None:
    outcome = run([["py", "<", 1]], True)
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2002"
    assert "bool" in outcome.reason


@pytest.mark.covers("py", "==")
def test_a_written_null_is_a_real_operand() -> None:
    """A parameter slot that is written takes the value it carries, even when it is ``null``."""
    assert run([["py", "==", None]], None) == Ok(True)
    assert run([["py", "in", [None]]], None) == Ok(True)


# ---------------------------------------------------------------- membership


@pytest.mark.covers("py", "in")
def test_in_looks_the_value_up_in_a_list() -> None:
    assert run([["py", "in", ["a", "b", "c"]]], "b") == Ok(True)


@pytest.mark.covers("py", "in")
def test_in_looks_the_value_up_in_a_dict() -> None:
    assert run([["py", "in", {"status": 200}]], "status") == Ok(True)


@pytest.mark.covers("py", "in")
def test_in_accepts_a_list_of_allowed_values() -> None:
    """The "status is one of 200/301/302" shape, with Python's operand order."""
    assert run([["py", "in", [200, 301, 302]]], 301) == Ok(True)
    assert run([["py", "in", [200, 301, 302]]], 404) == Ok(False)


@pytest.mark.covers("py", "in")
def test_in_asks_whether_a_literal_is_a_substring() -> None:
    """`the URL contains /public/` keeps Python's order: the element goes in front."""
    chain = [
        ["py", "const", "/public/1681/a.html"],
        ["ctx", "set", "locals._url"],
        ["py", "const", "/public/"],
        ["py", "in", "$locals._url"],
    ]
    assert run(chain, "in") == Ok(True)


@pytest.mark.covers("py", "in")
def test_in_rejects_a_parameter_that_is_not_a_container() -> None:
    outcome = run([["py", "in", 7]], "x")
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2002"


@pytest.mark.covers("py", "in")
def test_in_membership_is_deep_equality() -> None:
    assert run([["py", "in", [{"a": 1}, {"b": 2}]]], {"b": 2}) == Ok(True)
    assert run([["py", "in", [{"a": 1}]]], {"a": 2}) == Ok(False)


# ---------------------------------------------------------------- selection


@pytest.mark.covers("py", "or")
def test_or_picks_the_first_non_empty_candidate() -> None:
    chain = [
        ["py", "const", ""],
        ["ctx", "set", "locals._a"],
        ["py", "const", "/p/1"],
        ["ctx", "set", "locals._b"],
        ["py", "or", ["$locals._a", "$locals._b"]],
    ]
    assert run(chain, "in") == Ok("/p/1")


@pytest.mark.covers("py", "or")
def test_or_answers_the_last_operand_when_every_candidate_is_falsy() -> None:
    """Python's answer, and the reason this action is not called `any`."""
    chain = [["py", "const", 0], ["ctx", "set", "locals._b"], ["py", "or", ["", "$locals._b"]]]
    assert run(chain, "in") == Ok(0)


@pytest.mark.covers("py", "or")
def test_or_over_an_empty_array() -> None:
    assert run([["py", "or", []]], "in") == Ok("in")


@pytest.mark.covers("py", "or")
def test_or_rejects_a_parameter_that_is_not_an_array() -> None:
    chain = [["py", "const", "x"], ["ctx", "set", "locals._a"], ["py", "or", "$locals._a"]]
    outcome = run(chain, "in")
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2002"
    assert "str" in outcome.reason


@pytest.mark.covers("py", "and")
def test_and_answers_the_first_falsy_operand() -> None:
    chain = [
        ["py", "const", ""],
        ["ctx", "set", "locals._b"],
        ["py", "and", [{"t": 1}, "$locals._b"]],
    ]
    assert run(chain, "in") == Ok("")


@pytest.mark.covers("py", "and")
def test_and_over_an_empty_array() -> None:
    assert run([["py", "and", []]], "in") == Ok("in")


@pytest.mark.covers("py", "or")
def test_a_boolean_pair_still_answers_a_boolean() -> None:
    """Selection and judgement are the same action: booleans in, boolean out."""
    chain = [
        ["py", "const", False],
        ["ctx", "set", "locals._a"],
        ["py", "const", True],
        ["ctx", "set", "locals._b"],
        ["py", "or", ["$locals._a", "$locals._b"]],
    ]
    assert run(chain, "in") == Ok(True)


@pytest.mark.covers("py", "!=")
def test_negation_is_not_equal_against_a_boolean() -> None:
    """There is no `not` action: one boolean producer plus `!=` covers negation."""
    chain = [["py", "in", ["x"]], ["py", "!=", True]]
    assert run(chain, "y") == Ok(True)
    assert run(chain, "x") == Ok(False)


@pytest.mark.covers("py", "or")
def test_an_unreadable_candidate_fails_before_or_runs() -> None:
    """`or` falls back for present-but-empty candidates, not for a path that cannot be read."""
    absent = [["py", "or", ["$locals._a", "fallback"]]]
    outcome = run(absent, "in")
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2001"
    present = [["py", "const", ""], ["ctx", "set", "locals._a"], *absent]
    assert run(present, "in") == Ok("fallback")


# ---------------------------------------------------------------- existence


@pytest.mark.covers("css", "exists")
def test_css_exists_on_a_matching_structure() -> None:
    pytest.importorskip("selectolax")
    assert run([["css", "exists", "ul.list li"]], HTML) == Ok(True)


@pytest.mark.covers("css1", "exists")
def test_css1_exists_on_a_matching_structure() -> None:
    pytest.importorskip("selectolax")
    assert run([["css1", "exists", "ul.list li"]], HTML) == Ok(True)


@pytest.mark.covers("css", "exists")
def test_css_exists_is_false_when_nothing_matches() -> None:
    """`exists` answers a boolean, so no predicate has to reason about an empty value."""
    pytest.importorskip("selectolax")
    assert run([["css", "exists", ".nope"]], HTML) == Ok(False)


@pytest.mark.covers("css", "exists")
def test_nodes_yields_an_empty_list() -> None:
    """`exists` is a boolean view of the same fact; `nodes` answers the shape's empty value."""
    pytest.importorskip("selectolax")
    assert run([["css", "nodes", ".nope"]], HTML) == Ok([])


@pytest.mark.covers("py", "or")
def test_an_object_operand_list_is_a_compile_error() -> None:
    with pytest.raises(Up2Error) as info:
        compile_field([["py", "or", {"a": 1}]])
    assert info.value.diagnostic.code == "UP2-E1005"
