"""The ``node`` stage: a chain calls another node of the same story (design doc 03 §5.2)."""

from __future__ import annotations

from typing import Any

import pytest

from uniparser2 import Up2Error, compile_story, run
from uniparser2.core import registry

COVERS_PAIRS = (("node", "call"),)


def _story(nodes: dict[str, Any]) -> dict[str, Any]:
    return {"nodes": nodes}


def _compile_error(story: Any) -> Any:
    with pytest.raises(Up2Error) as info:
        compile_story(story)
    return info.value.diagnostic


def test_the_operator_is_registered() -> None:
    instance = registry.get("node")
    assert instance is not None
    assert instance.arity == 2


def test_a_named_node_is_called_with_the_current_value() -> None:
    story = _story({"a": [["py", "upper"], ["node", "b"]], "b": [["py", "strip"]]})
    assert run(story, "a", " x ") == "X"


def test_the_call_shares_the_callers_locals() -> None:
    story = _story(
        {
            "a": [["py", "strip"], ["ctx", "set", "locals.t"], ["node", "b"]],
            "b": {"seen": [["ctx", "get", "locals.t"]]},
        }
    )
    assert run(story, "a", " x ") == {"seen": "x"}


def test_a_node_call_inside_each_runs_per_element() -> None:
    story = _story(
        {
            "top": [["py", "const", ["a", "b"]], ["each", [["node", "upper"]]]],
            "upper": [["py", "upper"]],
        }
    )
    assert run(story, "top") == ["A", "B"]


def test_an_unknown_name_lists_the_nodes() -> None:
    diagnostic = _compile_error(_story({"a": [["node", "gone"]], "b": []}))
    assert diagnostic.code == "UP2-E1016"
    assert diagnostic.allowed == ("a", "b")


def test_a_three_slot_node_stage_is_rejected() -> None:
    assert _compile_error(_story({"a": [["node", "a", "x"]], "b": []})).code == "UP2-E1004"


def test_a_cycle_is_rejected() -> None:
    assert _compile_error(_story({"a": [["node", "b"]], "b": [["node", "a"]]})).code == (
        "UP2-E1017"
    )
