"""The trace: one event per evaluated stage, and a node call names its callee (design doc 06 §5.1).

The cases pin the design points of `06` §5.1 — values are not sent back in full, the parameters are
the **compiled** ones, fan-out is locatable, and a failed stage has a starting point — plus what a
tracing layer owes its caller: a run that asks for no trace records nothing and behaves exactly as
it did before.

The story exercises a node call, an `each` whose child chain calls two nodes per element, and a
field map, so the event's `node` and `item` are both visible.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from uniparser2 import (
    Failed,
    Ok,
    Scope,
    Trace,
    Up2Error,
    compile_field,
    eval_field,
    run,
)

pytest.importorskip("selectolax")

_DOC = (
    "<ul>"
    '<li><a href="/p/1">one</a></li>'
    '<li><a href="/p/2">two</a></li>'
    '<li><a href="/p/3">three</a></li>'
    "</ul>"
)

_STORY: dict[str, Any] = {
    "globals": {"base": "https://x/"},
    "nodes": {
        "top": [
            ["node", "links"],
            ["each", [["node", "fetch_page"], ["node", "page"]]],
        ],
        "links": [
            ["udf", "fetch"],
            ["py", "getattr", "text"],
            ["css", "nodes", "li"],
            [
                "each",
                {
                    "url": [["css1", "@href", "a"], ["py", "urljoin", "$globals.base"]],
                    "title": [["css1", "text", "a.nope"]],
                },
            ],
        ],
        "fetch_page": [["py", "getitem", "url"], ["udf", "fetch"]],
        "page": {
            "body": [["py", "getattr", "text"]],
            "final": [["py", "getattr", "url"]],
        },
    },
}


@dataclass(slots=True)
class _Response:
    """A stand-in host object: what an HTTP client would hand over."""

    text: str
    url: str


def _fetch(request: Any) -> _Response:
    if isinstance(request, str):
        text = _DOC if request.endswith("list.html") else f"<h1>{request}</h1>"
        return _Response(text, request)
    return _Response(f"<h1>{request['url']}</h1>", request["url"])


def _rows(trace: Trace) -> list[tuple[Any, ...]]:
    """``(seq, node, field, item, stage, state)`` of every event, in evaluation order."""
    return [
        (event.seq, event.node, event.field, event.item, event.stage, event.state)
        for event in trace.events
    ]


def _run_story(story: dict[str, Any], seed: str) -> tuple[Trace, Any]:
    trace = Trace()
    product = run(story, "top", seed, udfs={"fetch": _fetch}, trace=trace)
    return trace, product


# ---------------------------------------------------------------- the shape of a whole run


def test_one_event_per_evaluated_stage_in_evaluation_order() -> None:
    trace, product = _run_story(_STORY, "https://x/list.html")
    assert product == [
        {"body": "<h1>https://x/p/1</h1>", "final": "https://x/p/1"},
        {"body": "<h1>https://x/p/2</h1>", "final": "https://x/p/2"},
        {"body": "<h1>https://x/p/3</h1>", "final": "https://x/p/3"},
    ]
    # `links` runs first: fetch, read the text, select the items, then one dictionary per item.
    assert [event.node for event in trace.events[:4]] == ["links"] * 4
    assert (trace.events[0].op, trace.events[0].action) == ("udf", "fetch")
    assert trace.events[1].stage == 1
    assert trace.events[2].stage == 2
    # The url chain has two stages, so its field name repeats; the first stage of each chain is
    # enough to see the per-element order.
    fields = [
        (event.field, event.item)
        for event in trace.events
        if event.node == "links" and event.field is not None and event.stage == 0
    ]
    assert fields == [("url", 0), ("title", 0), ("url", 1), ("title", 1), ("url", 2), ("title", 2)]
    # The page node's events are named after the callee and numbered by the fan-out element.
    page = [(event.field, event.item) for event in trace.events if event.node == "page"]
    assert page == [
        ("body", 0),
        ("final", 0),
        ("body", 1),
        ("final", 1),
        ("body", 2),
        ("final", 2),
    ]
    assert all(event.seq == index for index, event in enumerate(trace.events, start=1))


def test_a_node_call_is_named_by_the_callee_and_restores_the_caller() -> None:
    trace, _ = _run_story(_STORY, "https://x/list.html")
    # The `["node","links"]` stage itself is recorded under the caller after the callee returns.
    first_top = next(event for event in trace.events if event.node == "top")
    assert (first_top.op, first_top.action) == ("node", "call")
    assert first_top.stage == 0


def test_the_seq_of_an_event_is_its_key_in_the_value_store() -> None:
    trace, _ = _run_story(_STORY, "https://x/list.html")
    assert [event.seq for event in trace.events] == list(range(1, len(trace) + 1))
    assert trace.get_value(1, side="input") == "https://x/list.html"
    assert trace.get_value(1).text == _DOC


# ---------------------------------------------------------------- the four design points


def test_the_parameters_are_the_compiled_ones() -> None:
    """A default the author did not write is visible, and a reference stays a reference."""
    trace = Trace()
    chain = [["css1", "@href", "a"], ["py", "urljoin", "$globals.base"]]
    outcome = eval_field(
        compile_field(chain),
        '<a href="/p/1">one</a>',
        scope=Scope(globals={"base": "https://x/"}),
        trace=trace,
    )
    assert outcome == Ok("https://x/p/1")
    assert trace.events[0].params == {
        "attr": {"kind": "lit", "value": "href"},
        "selector": {"kind": "lit", "value": "a"},
    }
    assert trace.events[1].params == {"base": {"kind": "ref", "target": "globals.base"}}


def test_a_function_with_no_argument_compiles_to_no_parameters() -> None:
    """``["py","len"]`` writes the empty placeholder, and the compiled parameters say so."""
    trace = Trace()
    assert eval_field(compile_field([["py", "len"]]), [1, 2], trace=trace) == Ok(2)
    assert trace.events[0].params == {}


def test_a_container_parameter_is_walked_element_by_element() -> None:
    """A positional list and a named object both arrive as the parameters they were mapped to."""
    listed = Trace()
    assert eval_field(compile_field([["py", "in", [200, 301]]]), 301, trace=listed) == Ok(True)
    assert listed.events[0].params == {
        "container": [{"kind": "lit", "value": 200}, {"kind": "lit", "value": 301}]
    }
    named = Trace()
    assert eval_field(compile_field([["re", "search", ["(a)", 1]]]), "a", trace=named) == Ok("a")
    assert named.events[0].params == {
        "pattern": {"kind": "lit", "value": "(a)"},
        "group": {"kind": "lit", "value": 1},
    }


def test_the_each_parameter_carries_its_compiled_field_map() -> None:
    """The sub-chains of a fan-out are part of the stage's compiled parameters, not a black box."""
    trace = Trace()
    eval_field(compile_field([["each", {"n": [["py", "len"]]}]]), ["ab"], trace=trace)
    assert len(trace.events) == 2
    inner, each = trace.events
    assert (inner.field, inner.item, inner.stage) == ("n", 0, 0)
    assert (each.field, each.item, each.stage, each.action) == (None, None, 0, "each")
    assert each.params == {
        "fields": {
            "kind": "fields",
            "fields": {
                "n": {
                    "kind": "chain",
                    "stages": [{"op": "py", "action": "len", "params": {}}],
                }
            },
        }
    }


def test_a_large_value_is_truncated_and_the_whole_one_is_fetched_by_seq() -> None:
    text = "a" * 300
    trace = Trace()
    assert eval_field(compile_field([["py", "upper"]]), text, trace=trace) == Ok(text.upper())
    event = trace.events[0]
    assert event.input.type == "str"
    assert event.input.size == len(text) + 2
    assert event.input.preview == f'"{text}"'[:200] + "...(+102)"
    assert trace.get_value(event.seq, side="input") == text
    assert trace.get_value(event.seq) == text.upper()


def test_a_no_match_output_is_a_viewable_empty_value() -> None:
    trace = Trace()
    assert eval_field(compile_field([["css1", "text", "div.nope"]]), _DOC, trace=trace) == Ok("")
    event = trace.events[0]
    assert (event.state, event.detail) == ("Ok", None)
    assert (event.output.type, event.output.preview) == ("str", '""')


def test_a_failing_stage_carries_its_code_and_reason() -> None:
    trace = Trace()
    with pytest.raises(Up2Error) as info:
        run({"nodes": {"bad": [["py", "int"]]}}, "bad", "not-a-number", trace=trace)
    assert info.value.diagnostic.code == "UP2-E2005"
    event = trace.events[-1]
    assert (event.node, event.field, event.stage, event.state) == ("bad", None, 0, "Failed")
    assert event.detail is not None
    assert event.detail["code"] == "UP2-E2005"
    assert "invalid literal" in event.detail["reason"]
    assert (event.output.type, event.output.preview) == ("null", "null")


def test_a_failed_stage_ends_its_chain_and_the_rest_is_not_evaluated() -> None:
    trace = Trace()
    outcome = eval_field(compile_field([["py", "upper"], ["py", "strip"]]), 42, trace=trace)
    assert isinstance(outcome, Failed)
    assert [(event.stage, event.state) for event in trace.events] == [(0, "Failed")]


# ---------------------------------------------------------------- nothing is collected unasked


def test_a_run_without_a_trace_records_nothing_and_answers_the_same() -> None:
    stamped = Trace()
    traced = run(_STORY, "top", "https://x/list.html", udfs={"fetch": _fetch}, trace=stamped)
    untraced = run(_STORY, "top", "https://x/list.html", udfs={"fetch": _fetch})
    assert traced == untraced
    assert len(stamped) > 0
    assert eval_field(compile_field([["py", "strip"]]), " a ") == Ok("a")


def test_every_fan_out_numbers_its_own_elements() -> None:
    """A second fan-out starts at 0 again: `item` is a position, not a run-wide counter."""
    trace = Trace()
    chain = [
        ["each", {"n": [["py", "len"]]}],
        ["each", {"m": [["py", "or", [""]]]}],
    ]
    assert eval_field(compile_field(chain), ["ab", "cd"], trace=trace) == Ok(
        [{"m": {"n": 2}}, {"m": {"n": 2}}]
    )
    assert _rows(trace) == [
        (1, None, "n", 0, 0, "Ok"),
        (2, None, "n", 1, 0, "Ok"),
        (3, None, None, None, 0, "Ok"),
        (4, None, "m", 0, 0, "Ok"),
        (5, None, "m", 1, 0, "Ok"),
        (6, None, None, None, 1, "Ok"),
    ]


def test_a_child_scope_carries_its_own_iteration() -> None:
    """A fan-out operator hands each element its own scope, which says which element it is."""
    root = Scope()
    children = [root.child(position) for position in range(3)]
    assert [child.iteration for child in children] == [0, 1, 2]
    assert root.iteration is None
    assert root.child().iteration is None
    assert children[0].child(7).iteration == 7
