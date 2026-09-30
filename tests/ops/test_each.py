"""Behaviour assertions for ``each`` (the chain-iteration capability, design doc 03 §4).

``each`` is the one iteration construct: the stage above produces a list, the field map turns every
element into a dictionary. The cases below follow the order of the delta spec: the shape of the
result, the field map as a per-element program, the ``_``-prefixed locals, one element's scope, the
failure rule, the compile-time rejections and the input limit.
"""

from __future__ import annotations

from typing import Any

import pytest

from uniparser2 import Failed, Missing, Ok, Outcome, Policy, Up2Error, compile_field, eval_field

# `drop` keeps a missing value visible as `Missing` instead of turning it into "", which is what the
# scope and failure cases assert.
DROP = Policy(on_missing="drop")


def run(chain: Any, value: Any, *, policy: Policy = DROP) -> Outcome:
    return eval_field(compile_field(chain), value, policy=policy)


def diagnostic(chain: Any) -> Any:
    with pytest.raises(Up2Error) as info:
        compile_field(chain)
    return info.value.diagnostic


@pytest.mark.covers("each", "each")
def test_one_dictionary_per_element() -> None:
    chain = [["each", {"n": [["py", "len", ""]], "u": [["py", "upper", ""]]}]]
    assert run(chain, ["ab", "cd"]) == Ok([{"n": 2, "u": "AB"}, {"n": 2, "u": "CD"}])


@pytest.mark.covers("each", "each")
def test_empty_list_is_an_empty_list() -> None:
    assert run([["each", {"n": [["py", "len", ""]]}]], []) == Ok([])


@pytest.mark.covers("each", "each")
def test_input_order_is_preserved() -> None:
    assert run([["each", {"raw": [["py", "strip", ""]]}]], ["b", "a"]) == Ok(
        [{"raw": "b"}, {"raw": "a"}]
    )


@pytest.mark.covers("each", "each")
def test_a_non_list_input_is_a_type_error() -> None:
    outcome = run([["each", {"n": [["py", "len", ""]]}]], {"a": 1})
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2002"
    assert "dict" in outcome.reason


@pytest.mark.covers("each", "each")
def test_a_missing_input_short_circuits_the_stage() -> None:
    """``each`` does not accept a missing value: the shared stage rule applies."""
    outcome = run([["ctx", "get", "locals.nope"], ["each", {"n": [["py", "len", ""]]}]], ["a"])
    assert isinstance(outcome, Missing)


@pytest.mark.covers("each", "each")
def test_a_collected_node_set_is_parsed_per_element() -> None:
    pytest.importorskip("selectolax")
    html = '<ul><li><a href="/a1">T1</a></li><li><a href="/a2">T2</a></li></ul>'
    chain = [
        ["css", "nodes", "li"],
        ["each", {"title": [["css1", "text", "a"]], "href": [["css1", "@href", "a"]]}],
    ]
    assert run(chain, html) == Ok([{"title": "T1", "href": "/a1"}, {"title": "T2", "href": "/a2"}])


@pytest.mark.covers("each", "each")
def test_a_later_field_reads_what_an_earlier_field_stored() -> None:
    chain = [["each", {"_raw": [["py", "strip", ""]], "seen": [["ctx", "get", "locals._raw"]]}]]
    assert run(chain, ["  a  "]) == Ok([{"seen": "a"}])


@pytest.mark.covers("each", "each")
def test_a_local_field_never_enters_the_dictionary() -> None:
    chain = [
        [
            "each",
            {
                "_t": [["py", "strip", ""]],
                "a": [["ctx", "get", "locals._t"]],
                "b": [["ctx", "get", "locals._t"], ["py", "upper", ""]],
            },
        ]
    ]
    assert run(chain, [" x "]) == Ok([{"a": "x", "b": "X"}])


@pytest.mark.covers("each", "each")
def test_an_element_local_shadows_the_calling_scope() -> None:
    chain = [
        ["ctx", "set", "locals.t"],
        [
            "each",
            {
                "seen": [
                    ["py", "upper", ""],
                    ["ctx", "set", "locals.t"],
                    ["ctx", "get", "locals.t"],
                ]
            },
        ],
    ]
    assert run(chain, ["a"]) == Ok([{"seen": "A"}])


@pytest.mark.covers("each", "each")
def test_an_element_reads_a_value_from_the_calling_scope() -> None:
    chain = [
        ["ctx", "set", "locals.base"],
        ["each", {"base": [["ctx", "get", "locals.base"]]}],
    ]
    assert run(chain, ["a"]) == Ok([{"base": ["a"]}])


@pytest.mark.covers("each", "each")
def test_an_element_local_does_not_outlive_the_element() -> None:
    chain = [["each", {"_t": [["py", "strip", ""]]}], ["ctx", "get", "locals._t"]]
    outcome = run(chain, ["a"])
    assert isinstance(outcome, Missing)


@pytest.mark.covers("each", "each")
def test_an_element_is_kept_even_when_every_field_is_absent() -> None:
    chain = [["each", {"n": [["ctx", "get", "locals.nope"]]}]]
    assert run(chain, ["a", "b"]) == Ok([{}, {}])


@pytest.mark.covers("each", "each")
def test_a_failing_stage_propagates_its_own_code() -> None:
    outcome = run([["each", {"first": [["py", "getitem", "0"]]}]], ["ab"])
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2002"


@pytest.mark.covers("each", "each")
def test_nested_each_stages_iterate_level_by_level() -> None:
    chain = [["each", {"lens": [["each", {"n": [["py", "len", ""]]}]]}]]
    assert run(chain, [["a", "b"], ["c"]]) == Ok(
        [{"lens": [{"n": 1}, {"n": 1}]}, {"lens": [{"n": 1}]}]
    )


@pytest.mark.covers("each", "each")
def test_the_iteration_limit_is_checked_before_evaluation() -> None:
    """The elements below would fail anyway, so the reported code proves the order."""
    outcome = run([["each", {"first": [["py", "getitem", "0"]]}]], ["a"] * 10_001)
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2012"


@pytest.mark.covers("each", "each")
def test_an_argument_that_is_not_an_object_is_a_schema_error() -> None:
    info = diagnostic(["each", "title"])
    assert info.code == "UP2-E1005"
    assert info.pointer == "/0/1/fields"
    assert '"title"' in info.fix


@pytest.mark.covers("each", "each")
def test_an_unknown_operator_inside_a_sub_chain_points_into_the_map() -> None:
    info = diagnostic([["each", {"title": [["nope", "text", ""]]}]])
    assert info.code == "UP2-E1001"
    assert info.pointer == "/0/1/fields/title/0/0"


@pytest.mark.covers("each", "each")
def test_a_wrong_stage_length_inside_a_sub_chain_points_into_the_map() -> None:
    info = diagnostic([["each", {"title": [["py"]]}]])
    assert info.code == "UP2-E1004"
    assert info.pointer == "/0/1/fields/title/0"


@pytest.mark.covers("each", "each")
def test_a_field_map_nested_too_deeply_is_a_limit_error() -> None:
    chain: Any = [["py", "strip", ""]]
    for field in ("d", "c", "b", "a"):
        chain = [["each", {field: chain}]]
    assert diagnostic(chain).code == "UP2-E1012"


@pytest.mark.covers("each", "each")
def test_three_nested_field_maps_are_still_accepted() -> None:
    chain = [["each", {"a": [["each", {"b": [["each", {"c": [["py", "strip", ""]]}]]}]]}]]
    assert run(chain, [[[" x "]]]) == Ok([{"a": [{"b": [{"c": "x"}]}]}])


@pytest.mark.covers("each", "each")
def test_a_sub_chain_respects_the_stage_limit() -> None:
    info = diagnostic([["each", {"t": [["py", "strip", ""]] * 33}]])
    assert info.code == "UP2-E1012"
    assert info.pointer == "/0/1/fields/t"


@pytest.mark.covers("each", "each")
def test_an_empty_field_map_is_a_schema_error() -> None:
    """Every element would be an empty dictionary, so the map is a typo rather than a chain."""
    info = diagnostic([["each", {}]])
    assert info.code == "UP2-E1005"
    assert info.pointer == "/0/1/fields"
    assert "at least one field" in info.fix


@pytest.mark.covers("each", "each")
@pytest.mark.parametrize("name", ["_a.b", "a.b", ""])
def test_a_field_name_a_reference_cannot_address_is_a_schema_error(name: str) -> None:
    """A path splits on `.`, so such a key would be computed and then silently unreachable."""
    info = diagnostic([["each", {name: [["py", "strip", ""]]}]])
    assert info.code == "UP2-E1005"
    assert info.pointer == f"/0/1/fields/{name}"
    assert repr(name) in info.fix


@pytest.mark.covers("each", "each")
def test_a_field_map_over_the_field_bound_is_a_limit_error() -> None:
    fields = {f"f{index}": [["py", "strip", ""]] for index in range(257)}
    info = diagnostic([["each", fields]])
    assert info.code == "UP2-E1012"
    assert info.pointer == "/0/1/fields"
    assert "257" in info.message
    assert "MAX_FIELDS_PER_MAP=256" in info.message


@pytest.mark.covers("each", "each")
def test_a_field_map_at_the_field_bound_is_accepted() -> None:
    fields = {f"f{index}": [["py", "strip", ""]] for index in range(256)}
    assert run([["each", fields]], [" a "]) == Ok([dict.fromkeys(fields, "a")])


@pytest.mark.covers("each", "each")
def test_a_missing_key_does_not_fall_through_to_an_outer_name() -> None:
    """The inner element owns `_a`, so a key missing under it is a miss, not the outer `_a`'s."""
    chain = [
        [
            "each",
            {
                "_a": [["const", {"b": 1}]],
                "kids": [
                    [
                        "each",
                        {
                            "_a": [["const", {"c": 2}]],
                            "seen": [["ctx", "get", "locals._a.b"]],
                        },
                    ]
                ],
            },
        ]
    ]
    assert run(chain, [["x"]]) == Ok([{"kids": [{}]}])


@pytest.mark.covers("each", "each")
def test_the_chain_round_trips_through_dumps() -> None:
    chain = [["each", {"n": [["py", "len", ""]]}]]
    assert compile_field(chain).dumps() == '[["each",{"n":[["py","len",""]]}]]'
