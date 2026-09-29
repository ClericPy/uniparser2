"""Serialization round-trip and "tests are the contract" (design docs 00 §2-N2, 05 §4.3).

Two assertions:
- ``dumps(loads(x)) == dumps(x)``: the canonical form is a **fixed point**;
- a second round-trip is character-for-character identical: breaking the serialization format of a
  chain turns red immediately (the approach of essence §C).
"""

from __future__ import annotations

from typing import Any

import pytest

from uniparser2 import dumps, loads

CHAINS: tuple[Any, ...] = (
    [["py", "strip", ""]],
    [["json", "data.html"]],
    [["const", "article"]],
    [["py", "int", ""]],
    [["re", "group", {"pattern": "(a)-(b)", "group": 2}]],
    [
        ["py", "upper", ""],
        ["ctx", "set", "locals._up"],
        ["py", "lower", ""],
        ["ctx", "get", "locals._up"],
    ],
    [["ctx", "map", {"title": "locals._t", "base": "globals.base"}]],
    [["py", "urljoin", "$globals.base_url"]],
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
    assert loads('[["py","strip",""]]') == loads([["py", "strip", ""]])
    assert loads([["py", "strip", ""]]) == loads(dumps([["py", "strip", ""]]))


def test_loads_single_stage_sugar_matches_wrapped_form() -> None:
    assert loads(["py", "strip", ""]) == loads([["py", "strip", ""]])


def test_two_slot_and_three_slot_forms_are_preserved() -> None:
    """2-slot operators (``const``/``json``) and 3-slot operators (``py``) keep their length."""
    assert dumps(loads([["const", "article"]])) == '[["const","article"]]'
    assert dumps(loads([["json", "data.html"]])) == '[["json","data.html"]]'
    assert dumps(loads([["py", "strip", ""]])) == '[["py","strip",""]]'


def test_non_ascii_is_not_escaped() -> None:
    assert "café" in dumps(loads([["const", "café"]]))


def test_empty_chain_is_rejected() -> None:
    from uniparser2 import Up2Error

    with pytest.raises(Up2Error) as info:
        loads([])
    assert info.value.diagnostic.code == "UP2-E1004"
