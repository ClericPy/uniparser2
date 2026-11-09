"""The trace: one event per evaluated stage, plus one per effect suspension (`06` §5.1, `03` §4.4).

The cases pin the four design points of `06` §5.1 — values are not sent back in full, the parameters
are the **compiled** ones, fan-out is locatable, and `Missing` has a starting point — plus the two
things a tracing layer owes its caller: a suspension is an event carrying what was handed out, and a
run that asks for no trace records nothing and behaves exactly as it did before.

The story below is the one shape that exercises both fan-out kinds at once: a seed `Request`, a
`RequestBatch` whose tasks come out of an `each` field map (so `item` numbers the list elements), a
receiving step that runs once per answer (so `item` numbers the answers), and a final `call`.
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
    start,
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
    "entry": "seed",
    "steps": [
        {
            "name": "seed",
            "body": {"url": "$in"},
            "type": "Request",
            "next": "links",
        },
        {
            "name": "links",
            "body": {
                "items": [
                    ["py", "getattr", "text"],
                    ["css", "nodes", "li"],
                    [
                        "each",
                        {
                            "url": [
                                ["css1", "@href", "a"],
                                ["py", "urljoin", "$globals.base"],
                            ],
                            "title": [["css1", "text", "a.nope"]],
                        },
                    ],
                ]
            },
            "type": "RequestBatch",
            "next": "page",
        },
        {
            "name": "page",
            "body": {
                "body": [["py", "getattr", "text"]],
                "final": [["py", "getattr", "url"]],
            },
            "type": "dict",
        },
        {
            "name": "store",
            "call": "host.store_books",
            "args": {"table": "books", "rows": "$in"},
            "type": "dict",
        },
    ],
    "collect": "store",
}


@dataclass(slots=True)
class Answer:
    """A stand-in host object: what an HTTP client would hand over (`03` §4.1)."""

    text: str
    url: str


def _rows(trace: Trace) -> list[tuple[Any, ...]]:
    """``(seq, step, field, item, stage, state)`` of every event, in evaluation order."""
    return [
        (event.seq, event.step, event.field, event.item, event.stage, event.state)
        for event in trace.events
    ]


def _run_story(story: dict[str, Any], seed: str) -> tuple[Trace, Any]:
    """Drive the whole story by hand (the CLI has no host): one request, one batch, one call."""
    trace = Trace()
    run = start(story, seed, trace=trace)
    assert run.go() == ("request", {"url": seed}, "links")
    batch = run.feed(Answer(_DOC, seed))
    assert batch[0] == "batch"
    tasks = batch[1]
    assert [task["url"] for task in tasks] == ["https://x/p/1", "https://x/p/2", "https://x/p/3"]
    call = run.feed([Answer(f"<h1>{index}</h1>", task["url"]) for index, task in enumerate(tasks)])
    assert call == (
        "call",
        "host.store_books",
        {
            "table": "books",
            # The fan-out rejoins once, so the `call` step's input is every answer's product.
            "rows": [
                {"body": "<h1>0</h1>", "final": "https://x/p/1"},
                {"body": "<h1>1</h1>", "final": "https://x/p/2"},
                {"body": "<h1>2</h1>", "final": "https://x/p/3"},
            ],
        },
    )
    # The exit step is the call, so the receipt is the run's only product.
    return trace, run.feed({"stored": 3})


# ---------------------------------------------------------------- the shape of a whole run


def test_one_event_per_evaluated_stage_in_evaluation_order() -> None:
    trace, done = _run_story(_STORY, "https://x/list.html")
    assert done == ("done", [{"stored": 3}])
    # The seed step's `parse` is a whole-chain reference: it does no work, so it records no stage
    # of its own and the run opens with the request suspension (`03` §2).
    assert _rows(trace) == [
        (1, "seed", None, None, None, "Ok"),  # the request suspension
        (2, "links", "items", None, 0, "Ok"),
        (3, "links", "items", None, 1, "Ok"),
        # The `each` field map runs per element, in input order; `title` misses for every one.
        (4, "links", "url", 0, 0, "Ok"),
        (5, "links", "url", 0, 1, "Ok"),
        (6, "links", "title", 0, 0, "Ok"),
        (7, "links", "url", 1, 0, "Ok"),
        (8, "links", "url", 1, 1, "Ok"),
        (9, "links", "title", 1, 0, "Ok"),
        (10, "links", "url", 2, 0, "Ok"),
        (11, "links", "url", 2, 1, "Ok"),
        (12, "links", "title", 2, 0, "Ok"),
        # The `each` stage itself is recorded once its sub-chains are done.
        (13, "links", "items", None, 2, "Ok"),
        (14, "links", None, None, None, "Ok"),  # the batch suspension
        # The receiving step runs once per answer, numbered by the answer's position.
        (15, "page", "body", 0, 0, "Ok"),
        (16, "page", "final", 0, 0, "Ok"),
        (17, "page", "body", 1, 0, "Ok"),
        (18, "page", "final", 1, 0, "Ok"),
        (19, "page", "body", 2, 0, "Ok"),
        (20, "page", "final", 2, 0, "Ok"),
        (21, "store", None, None, None, "Ok"),  # the call suspension
    ]


def test_the_seq_of_an_event_is_its_key_in_the_value_store() -> None:
    trace, _ = _run_story(_STORY, "https://x/list.html")
    assert [event.seq for event in trace.events] == list(range(1, len(trace) + 1))
    assert len(trace) == 21
    # The whole value behind a preview: the request suspension's input is the run's own seed.
    assert trace.get_value(1, side="input") == "https://x/list.html"


def test_the_effects_hand_over_what_the_host_must_answer() -> None:
    trace, _ = _run_story(_STORY, "https://x/list.html")
    effects = [event for event in trace.events if event.effect is not None]
    assert [event.effect for event in effects] == ["request", "batch", "call"]
    assert [event.state for event in effects] == ["Ok", "Ok", "Ok"]
    request, batch, call = effects
    # A request hands over one task; a batch hands over every task, and the host never sees `next`.
    assert request.output.preview == '{"url": "https://x/list.html"}'
    assert [task["url"] for task in trace.get_value(batch.seq)] == [
        "https://x/p/1",
        "https://x/p/2",
        "https://x/p/3",
    ]
    assert all("next" not in task for task in trace.get_value(batch.seq))
    # A `call` names the host function and carries the compiled `with` tree beside the arguments.
    assert call.action == "host.store_books"
    assert call.params == {
        "table": {"kind": "lit", "value": "books"},
        "rows": {"kind": "ref", "target": "in"},
    }
    assert trace.get_value(call.seq) == {
        "table": "books",
        "rows": [
            {"body": "<h1>0</h1>", "final": "https://x/p/1"},
            {"body": "<h1>1</h1>", "final": "https://x/p/2"},
            {"body": "<h1>2</h1>", "final": "https://x/p/3"},
        ],
    }


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
    # The action slot `@href` is a preset parameter, so it is part of what the engine understood.
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
    container = [["py", "in", [200, 301]]]
    assert eval_field(compile_field(container), 301, trace=listed) == Ok(True)
    assert listed.events[0].params == {
        "container": [{"kind": "lit", "value": 200}, {"kind": "lit", "value": 301}]
    }
    named = Trace()
    grouped = [["re", "search", ["(a)", 1]]]
    assert eval_field(compile_field(grouped), "a", trace=named) == Ok("a")
    assert named.events[0].params == {
        "pattern": {"kind": "lit", "value": "(a)"},
        "group": {"kind": "lit", "value": 1},
    }
    nested = Trace()
    fallback = [["py", "or", [{"a": 1, "b": 2}]]]
    assert eval_field(compile_field(fallback), None, trace=nested) == Ok({"a": 1, "b": 2})
    assert nested.events[0].params == {
        "operands": [{"a": {"kind": "lit", "value": 1}, "b": {"kind": "lit", "value": 2}}]
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
    assert event.input.size == len(text) + 2  # the JSON text of a string carries its quotes
    assert event.input.preview == f'"{text}"'[:200] + "...(+102)"
    assert trace.get_value(event.seq, side="input") == text
    assert trace.get_value(event.seq) == text.upper()


def test_a_no_match_output_is_a_viewable_empty_value() -> None:
    trace = Trace()
    outcome = eval_field(compile_field([["css1", "text", "div.nope"]]), _DOC, trace=trace)
    assert outcome == Ok("")
    event = trace.events[0]
    assert (event.state, event.detail) == ("Ok", None)
    assert (event.output.type, event.output.preview) == ("str", '""')


def test_a_failing_stage_carries_its_code_and_reason() -> None:
    trace = Trace()
    with pytest.raises(Up2Error) as info:
        start(
            {
                "entry": "bad",
                "steps": [{"name": "bad", "body": [["py", "int"]], "type": "int"}],
                "collect": "bad",
            },
            "not-a-number",
            trace=trace,
        ).go()
    assert info.value.diagnostic.code == "UP2-E2005"
    event = trace.events[-1]
    assert (event.step, event.field, event.stage, event.state) == ("bad", None, 0, "Failed")
    assert event.detail is not None
    assert event.detail["code"] == "UP2-E2005"
    assert "invalid literal" in event.detail["reason"]
    # A failed stage produced no value: the output says so instead of inventing one.
    assert (event.output.type, event.output.preview) == ("null", "null")


def test_a_failed_stage_ends_its_chain_and_the_rest_is_not_evaluated() -> None:
    trace = Trace()
    outcome = eval_field(compile_field([["py", "upper"], ["py", "strip"]]), 42, trace=trace)
    assert isinstance(outcome, Failed)
    assert [(event.stage, event.state) for event in trace.events] == [(0, "Failed")]


# ---------------------------------------------------------------- nothing is collected unasked


def test_a_run_without_a_trace_records_nothing_and_answers_the_same() -> None:
    stamped = Trace()
    traced = start(_STORY, "https://x/list.html", trace=stamped)
    assert traced.trace is stamped
    untraced = start(_STORY, "https://x/list.html")
    assert untraced.trace is None
    assert traced.go() == untraced.go()
    assert len(stamped) == 1  # the request suspension (the seed's chain is a reference)
    assert eval_field(compile_field([["py", "strip"]]), " a ") == Ok("a")


def test_every_fan_out_numbers_its_own_elements() -> None:
    """A second fan-out starts at 0 again: `item` is a position, not a run-wide counter.

    The second field map's chain takes the element it was handed and hands it back (`py.default`
    changes nothing an element that is not empty), which is what the removed identity stage used to
    spell -- a chain's first stage already receives the element (`02` §5).
    """
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
        (3, None, None, None, 0, "Ok"),  # the first `each` stage itself
        (4, None, "m", 0, 0, "Ok"),
        (5, None, "m", 1, 0, "Ok"),
        (6, None, None, None, 1, "Ok"),  # the second one
    ]


def test_a_child_scope_carries_its_own_iteration() -> None:
    """A fan-out operator hands each element its own scope, which says which element it is."""
    root = Scope()
    children = [root.child(position) for position in range(3)]
    assert [child.iteration for child in children] == [0, 1, 2]
    assert root.iteration is None
    assert root.child().iteration is None  # a scope taken without a fan-out position
    assert children[0].child(7).iteration == 7  # a nested fan-out numbers itself again
