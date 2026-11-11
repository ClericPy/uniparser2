"""Serialization round-trip and "tests are the contract" (design docs 00 §2-N2, 05 §4.3).

Two assertions:
- ``dumps(loads(x)) == dumps(x)``: the canonical form is a **fixed point**;
- a second round-trip is character-for-character identical: breaking the serialization format of a
  chain turns red immediately (the approach of essence §C).
"""

from __future__ import annotations

from typing import Any

import pytest

from uniparser2 import Up2Error, dumps, loads

CHAINS: tuple[Any, ...] = (
    [["py", "strip"]],
    [["json", "data.html"]],
    [["py", "const", "article"]],
    [["py", "int"]],
    [["re", "search", ["(a)-(b)", 2]]],
    [
        ["py", "upper"],
        ["ctx", "set", "locals._up"],
        ["py", "lower"],
        ["ctx", "get", "locals._up"],
    ],
    [["ctx", "dict", {"title": "locals._t", "base": "globals.base"}]],
    [["py", "urljoin", "$globals.base_url"]],
    [["try", "skip"], ["py", "int"]],
)


@pytest.mark.parametrize("chain", CHAINS, ids=[str(i) for i in range(len(CHAINS))])
def test_dumps_is_a_fixed_point(chain: Any) -> None:
    once = dumps(loads(chain))
    assert dumps(loads(once)) == once


@pytest.mark.parametrize("chain", CHAINS, ids=[str(i) for i in range(len(CHAINS))])
def test_second_round_trip_is_byte_identical(chain: Any) -> None:
    text = dumps(loads(chain))
    assert dumps(loads(text)) == text


def test_loads_accepts_text_and_structures() -> None:
    assert loads('[["py","strip"]]') == loads([["py", "strip"]])
    assert loads([["py", "strip"]]) == loads(dumps([["py", "strip"]]))


def test_loads_single_stage_sugar_matches_wrapped_form() -> None:
    assert loads(["py", "strip"]) == loads([["py", "strip"]])


def test_loads_accepts_the_source_by_keyword() -> None:
    """``loads`` is public (``core.__all__``), so its single parameter is not positional-only."""
    assert loads(source=[["py", "strip"]]) == loads([["py", "strip"]])


def test_two_slot_and_three_slot_forms_are_preserved() -> None:
    """2-slot operators (``const``/``json``) and 3-slot operators (``py``) keep their length."""
    assert dumps(loads([["py", "const", "article"]])) == '[["py","const","article"]]'
    assert dumps(loads([["json", "data.html"]])) == '[["json","data.html"]]'
    assert dumps(loads([["py", "strip"]])) == '[["py","strip"]]'


def test_non_ascii_is_not_escaped() -> None:
    assert "café" in dumps(loads([["py", "const", "café"]]))


def test_an_empty_chain_is_identity() -> None:
    """`[]` is the only identity form: it loads as no stages and dumps back as `[]`."""
    assert loads([]) == ()
    assert dumps(loads([])) == "[]"


@pytest.mark.parametrize(
    "text", ['[["py","const",Infinity]]', '[["py","const",-Infinity]]', '[["py","const",NaN]]']
)
def test_a_non_json_constant_is_rejected(text: str) -> None:
    """A chain is JSON data; Python's decoder takes these, JSON does not."""
    with pytest.raises(Up2Error) as info:
        loads(text)
    assert info.value.diagnostic.code == "UP2-E1004"


def test_malformed_text_is_e1004() -> None:
    """A syntax error is one more bad chain: the public loader answers a code, not a decoder."""
    with pytest.raises(Up2Error) as info:
        loads("not json")
    diagnostic = info.value.diagnostic
    assert diagnostic.code == "UP2-E1004"
    assert "is not valid JSON" in diagnostic.message
    assert diagnostic.fix


def test_dumps_refuses_a_non_finite_parameter() -> None:
    """``allow_nan=False``: never write text a strict JSON parser rejects."""
    with pytest.raises(Up2Error) as info:
        dumps([["py", "const", float("inf")]])
    assert info.value.diagnostic.code == "UP2-E1004"


def test_dumps_json_refuses_a_non_string_key() -> None:
    """``json.dumps`` would coerce ``1`` to ``"1"``; the writer refuses instead of changing data."""
    from uniparser2.core.values import dumps_json

    with pytest.raises(Up2Error) as info:
        dumps_json({1: "a"})
    assert info.value.diagnostic.code == "UP2-E1004"
    assert dumps_json((1, 2)) == "[1, 2]"  # a tuple is written as the array it stands for
