"""The story layer: compiling a site bundle and running it (design doc 03 §2-§5).

A story is data, so every structural mistake must fail at **compile time** with a code and a JSON
Pointer; the run then only evaluates. Two things are pinned here beyond the happy path: the shape of
each effect, and the rule that an answer resumes the **same** run (no hand-off).
"""

from __future__ import annotations

from typing import Any

import pytest

from uniparser2 import (
    Missing,
    Ok,
    Ref,
    Scope,
    Up2Error,
    compile_field,
    compile_story,
    eval_field,
    start,
)
from uniparser2.core.refs import RESERVED_ROOTS

_DOC = "<div><a href='/p/1'>one</a><a href='/p/2'>two</a></div>"


class Answer:
    """A stand-in host object: what an HTTP client would hand over."""

    __slots__ = ("text", "url")

    def __init__(self, text: str, url: str = "https://x/p/") -> None:
        self.text = text
        self.url = url


def _parse_story(**overrides: Any) -> dict[str, Any]:
    story: dict[str, Any] = {
        "steps": [
            {
                "name": "records",
                "parse": {"url": [["py", "id", ""]], "size": [["py", "len", ""]]},
                "type": "Record",
            }
        ],
        "exit": "records",
    }
    story.update(overrides)
    return story


def _compile_error(story: Any) -> str:
    with pytest.raises(Up2Error) as info:
        compile_story(story)
    return info.value.diagnostic.code


def _run_error(story: Any, value: Any = None) -> str:
    with pytest.raises(Up2Error) as info:
        start(story, value).next()
    return info.value.diagnostic.code


# ---------------------------------------------------------------- compiling a bundle


def test_a_minimal_story_compiles() -> None:
    story = compile_story(_parse_story())
    assert [step.name for step in story.steps] == ["records"]
    assert story.exit == "records"
    assert story.steps[0].type == "Record"


def test_a_bundle_must_be_an_object() -> None:
    assert _compile_error([]) == "UP2-E1005"


def test_an_unknown_bundle_key_is_rejected() -> None:
    """`chains` is the deleted table: a parse rule is a step, so the key is gone for good."""
    code = _compile_error(_parse_story(chains={"list": [["py", "strip", ""]]}))
    assert code == "UP2-E1005"


def test_steps_must_be_a_non_empty_array() -> None:
    assert _compile_error({"steps": [], "exit": "records"}) == "UP2-E1005"
    assert _compile_error({"exit": "records"}) == "UP2-E1005"


def test_exit_is_required_and_must_resolve() -> None:
    assert _compile_error({"steps": _parse_story()["steps"]}) == "UP2-E1005"
    assert _compile_error(_parse_story(exit="nope")) == "UP2-E1016"


def test_step_names_are_unique() -> None:
    story = _parse_story(
        steps=[
            {"name": "a", "parse": {"u": [["py", "id", ""]]}},
            {"name": "a", "parse": {"u": [["py", "id", ""]]}},
        ],
        exit="a",
    )
    assert _compile_error(story) == "UP2-E1009"


def test_a_step_name_may_not_be_a_reserved_root() -> None:
    for reserved in RESERVED_ROOTS:
        story = _parse_story(steps=[{"name": reserved, "parse": {"u": [["py", "id", ""]]}}])
        story["exit"] = reserved
        assert _compile_error(story) == "UP2-E1009"


def test_a_step_declares_exactly_one_of_parse_and_call() -> None:
    both = _parse_story(
        steps=[{"name": "a", "parse": {"u": [["py", "id", ""]]}, "call": "host.fn"}], exit="a"
    )
    assert _compile_error(both) == "UP2-E1005"
    neither = _parse_story(steps=[{"name": "a", "type": "dict"}], exit="a")
    assert _compile_error(neither) == "UP2-E1005"


def test_with_belongs_to_a_call_step() -> None:
    story = _parse_story(
        steps=[{"name": "a", "parse": {"u": [["py", "id", ""]]}, "with": {"t": 1}}], exit="a"
    )
    assert _compile_error(story) == "UP2-E1005"


def test_an_unknown_step_key_is_rejected() -> None:
    """The old `key` / `out` spellings are gone: `name` and `type` are the keys (03 §2.1)."""
    story = _parse_story(
        steps=[{"name": "a", "parse": {"u": [["py", "id", ""]]}, "out": "dict"}], exit="a"
    )
    assert _compile_error(story) == "UP2-E1005"


def test_next_is_required_on_a_request_step() -> None:
    story = _parse_story(
        steps=[{"name": "a", "parse": {"url": [["py", "id", ""]]}, "type": "Request"}], exit="a"
    )
    assert _compile_error(story) == "UP2-E1005"


def test_next_is_refused_on_a_step_that_produces_no_request() -> None:
    story = _parse_story(
        steps=[{"name": "a", "parse": {"u": [["py", "id", ""]]}, "next": "a"}], exit="a"
    )
    assert _compile_error(story) == "UP2-E1005"


def test_next_must_resolve_to_a_step() -> None:
    story = _parse_story(
        steps=[
            {"name": "a", "parse": {"url": [["py", "id", ""]]}, "type": "Request", "next": "gone"}
        ],
        exit="a",
    )
    assert _compile_error(story) == "UP2-E1016"


def test_the_step_limit_is_enforced() -> None:
    steps = [{"name": f"s{index}", "parse": {"u": [["py", "id", ""]]}} for index in range(65)]
    assert _compile_error({"steps": steps, "exit": "s0"}) == "UP2-E1012"


def test_an_empty_field_map_is_rejected() -> None:
    story = _parse_story(steps=[{"name": "a", "parse": {}, "type": "dict"}], exit="a")
    assert _compile_error(story) == "UP2-E1005"


# ---------------------------------------------------------------- running a story


def test_a_story_without_requests_finishes_at_once() -> None:
    run = start(_parse_story(), "u")
    assert run.next() == ("done", [{"url": "u", "size": 1}])


def test_done_is_idempotent_and_send_is_refused() -> None:
    run = start(_parse_story(), "u")
    assert run.next()[0] == "done"
    assert run.next() == run.next()
    with pytest.raises(ValueError, match="already done"):
        run.send("anything")


def test_a_request_suspends_the_run() -> None:
    story = {
        "steps": [
            {
                "name": "seed",
                "parse": {"url": [["py", "id", ""]]},
                "type": "Request",
                "next": "records",
            },
            {"name": "records", "parse": {"body": [["py", "getattr", "text"]]}, "type": "Record"},
        ],
        "exit": "records",
    }
    run = start(story, "https://x/list.html")
    assert run.next() == ("request", {"url": "https://x/list.html"}, "records")
    answer = Answer(_DOC)
    assert run.send(answer) == ("done", [{"body": _DOC}])
    assert run.next() == ("done", [{"body": _DOC}])


def test_the_answer_is_never_copied_or_converted() -> None:
    """The receiving step reads the host's own object: `$in` and `getattr` see the same instance."""
    story = {
        "steps": [
            {
                "name": "seed",
                "parse": {"url": [["py", "id", ""]]},
                "type": "Request",
                "next": "read",
            },
            {
                "name": "read",
                "parse": {
                    "final": [["py", "getattr", "url"]],
                    "resolved": [["const", "https://x/final"], ["py", "==", "$in.url"]],
                },
                "type": "Answer",
            },
        ],
        "exit": "read",
    }
    answer = Answer(_DOC, url="https://x/final")
    run = start(story, "https://x/list.html")
    run.next()
    # `$in.url` resolved against the host's own object: the receiving step's input is that object.
    assert run.send(answer) == ("done", [{"final": "https://x/final", "resolved": True}])


def test_a_step_product_that_is_not_json_stops_the_run() -> None:
    """A value may flow, but a step product must be JSON (03 §3.3, UP2-E2003)."""
    story = {
        "steps": [
            {
                "name": "seed",
                "parse": {"url": [["py", "id", ""]]},
                "type": "Request",
                "next": "keep",
            },
            {"name": "keep", "parse": [["py", "id", ""]], "type": "Answer"},
        ],
        "exit": "keep",
    }
    run = start(story, "seed")
    run.next()
    with pytest.raises(Up2Error) as info:
        run.send(Answer(_DOC))
    assert info.value.diagnostic.code == "UP2-E2003"


def test_a_batch_runs_the_receiving_step_once_per_answer_and_rejoins() -> None:
    story = {
        "steps": [
            {
                "name": "seed",
                "parse": {"url": [["py", "id", ""]]},
                "type": "Request",
                "next": "fan",
            },
            {
                "name": "fan",
                "parse": {"items": [["const", [{"url": "a"}, {"url": "b"}]]]},
                "type": "RequestBatch",
                "next": "page",
            },
            {"name": "page", "parse": [["py", "getattr", "text"]], "type": "Page"},
            {"name": "count", "parse": {"n": [["py", "len", ""]]}, "type": "dict"},
        ],
        "exit": "count",
    }
    run = start(story, "seed")
    assert run.next() == ("request", {"url": "seed"}, "fan")
    effect = run.send(Answer("seed page"))
    assert effect == ("batch", [{"url": "a"}, {"url": "b"}], "page")
    assert run.send([Answer("a page"), Answer("b page")]) == ("done", [{"n": 2}])


def test_a_task_may_override_next() -> None:
    story = {
        "steps": [
            {
                "name": "seed",
                "parse": {"url": [["py", "id", ""]]},
                "type": "Request",
                "next": "fan",
            },
            {
                "name": "fan",
                "parse": {
                    "items": [
                        ["const", [{"url": "a", "next": "left"}, {"url": "b", "next": "right"}]]
                    ]
                },
                "type": "RequestBatch",
                "next": "left",
            },
            {"name": "left", "parse": {"side": [["const", "left"]]}, "type": "dict"},
            {"name": "right", "parse": {"side": [["const", "right"]]}, "type": "dict"},
            {"name": "joined", "parse": {"n": [["py", "len", ""]]}, "type": "dict"},
        ],
        "exit": "joined",
    }
    run = start(story, "seed")
    run.next()
    effect = run.send(Answer("home"))
    assert effect == ("batch", [{"url": "a"}, {"url": "b"}], "left")
    # The host never sees `next`: it is the kernel's routing key. The tuple's second slot is a union
    # of every effect shape, so it goes through an explicitly typed variable (the device
    # ``tests/core/test_core_edges.py`` uses for a deliberate ``Any``).
    batch: Any = effect[1]
    assert all("next" not in task for task in batch)
    # The first task routes left, the second right; both products join and continue after `left`.
    assert run.send([Answer("x"), Answer("y")]) == ("done", [{"n": 2}])


def test_a_receiving_step_may_itself_produce_a_request() -> None:
    story = {
        "steps": [
            {
                "name": "seed",
                "parse": {"url": [["py", "id", ""]]},
                "type": "Request",
                "next": "gather",
            },
            {
                "name": "gather",
                "parse": {"items": [["const", [{"url": "a"}]]]},
                "type": "RequestBatch",
                "next": "page",
            },
            {
                "name": "page",
                "parse": {"url": [["py", "getattr", "url"]]},
                "type": "Request",
                "next": "record",
            },
            {"name": "record", "parse": {"body": [["py", "getattr", "text"]]}, "type": "Record"},
        ],
        "exit": "record",
    }
    run = start(story, "seed")
    run.next()
    assert run.send(Answer("home"))[0] == "batch"
    # The receiving step is itself a request: the run suspends again, inside the same fan-out.
    assert run.send([Answer("page 1")]) == (
        "request",
        {"url": "https://x/p/"},
        "record",
    )
    assert run.send(Answer("record body")) == ("done", [{"body": "record body"}])


def test_a_call_suspends_and_resumes_with_the_receipt() -> None:
    story = {
        "steps": [
            {"name": "records", "parse": {"url": [["py", "id", ""]]}, "type": "Record"},
            {
                "name": "store",
                "call": "host.store_records",
                "with": {"table": "records", "from": "$records.url"},
                "type": "dict",
            },
        ],
        "exit": "store",
    }
    run = start(story, "u")
    assert run.next() == ("call", "host.store_records", {"table": "records", "from": "u"})
    assert run.send({"stored": 1}) == ("done", [{"stored": 1}])


def test_an_exit_step_that_is_jumped_over_yields_an_empty_output() -> None:
    story = {
        "steps": [
            {
                "name": "seed",
                "parse": {"url": [["py", "id", ""]]},
                "type": "Request",
                "next": "last",
            },
            {"name": "skipped", "parse": {"u": [["py", "id", ""]]}, "type": "dict"},
            {"name": "last", "parse": {"u": [["py", "getattr", "text"]]}, "type": "dict"},
        ],
        "exit": "skipped",
    }
    run = start(story, "seed")
    assert run.next() == ("request", {"url": "seed"}, "last")
    assert run.send(Answer("home")) == ("done", [])


def test_a_failing_step_stops_the_run_with_its_code() -> None:
    story = _parse_story(
        steps=[
            {"name": "bad", "parse": [["py", "int", ""]], "type": "int"},
        ],
        exit="bad",
    )
    assert _run_error(story, "not-a-number") == "UP2-E2005"
    with pytest.raises(Up2Error) as info:
        start(story, "not-a-number").next()
    assert info.value.diagnostic.pointer == "/steps/0"


def test_a_missing_chain_product_is_null() -> None:
    """A selector that matched nothing is not an error: the step produced nothing, and it flows as
    null (an open question in the change's design)."""
    story = _parse_story(steps=[{"name": "a", "parse": [["css1", "text", "div.nope"]]}], exit="a")
    assert start(story, _DOC).next() == ("done", [None])


def test_a_batch_answer_of_the_wrong_size_is_a_host_error() -> None:
    story = {
        "steps": [
            {
                "name": "seed",
                "parse": {"url": [["py", "id", ""]]},
                "type": "Request",
                "next": "fan",
            },
            {
                "name": "fan",
                "parse": {"items": [["const", [{"url": "a"}, {"url": "b"}]]]},
                "type": "RequestBatch",
                "next": "page",
            },
            {"name": "page", "parse": [["py", "getattr", "text"]], "type": "Page"},
        ],
        "exit": "page",
    }
    run = start(story, "seed")
    run.next()
    run.send(Answer("home"))
    with pytest.raises(ValueError, match="2 answers"):
        run.send([Answer("only one")])


def test_a_batch_product_without_items_is_a_story_error() -> None:
    story = _parse_story(
        steps=[
            {
                "name": "bad",
                "parse": {"nope": [["py", "id", ""]]},
                "type": "RequestBatch",
                "next": "bad",
            }
        ],
        exit="bad",
    )
    assert _run_error(story, {"a": 1}) == "UP2-E2005"


def test_a_task_routing_to_an_unknown_step_fails() -> None:
    """A task's own `next` is data, so its target is checked when the batch is handed over."""
    story = _parse_story(
        steps=[
            {
                "name": "seed",
                "parse": {"url": [["py", "id", ""]]},
                "type": "Request",
                "next": "fan",
            },
            {
                "name": "fan",
                "parse": {"items": [["const", [{"url": "a", "next": "gone"}]]]},
                "type": "RequestBatch",
                "next": "fan",
            },
        ],
        exit="fan",
    )
    run = start(story, "seed")
    run.next()
    with pytest.raises(Up2Error) as info:
        run.send(Answer("home"))
    assert info.value.diagnostic.code == "UP2-E1016"


def test_a_request_product_that_is_not_an_object_is_a_story_error() -> None:
    story = _parse_story(
        steps=[{"name": "bad", "parse": [["const", 7]], "type": "Request", "next": "bad"}],
        exit="bad",
    )
    assert _run_error(story, "ignored") == "UP2-E2005"


def test_a_batch_task_that_is_not_an_object_is_a_story_error() -> None:
    story = _parse_story(
        steps=[
            {
                "name": "bad",
                "parse": {"items": [["const", [7]]]},
                "type": "RequestBatch",
                "next": "bad",
            }
        ],
        exit="bad",
    )
    assert _run_error(story, "ignored") == "UP2-E2005"


def test_the_run_exposes_its_story_and_input_and_can_be_closed() -> None:
    run = start(_parse_story(), "u")
    assert run.story.exit == "records"
    assert run.value == "u"
    run.close()


def test_a_step_must_be_an_object() -> None:
    assert _compile_error({"steps": [7], "exit": "records"}) == "UP2-E1005"


def test_a_step_with_a_non_string_call_is_rejected() -> None:
    assert _compile_error(_parse_story(steps=[{"name": "a", "call": 7}], exit="a")) == "UP2-E1005"


def test_a_globals_table_must_be_an_object() -> None:
    assert _compile_error(_parse_story(globals=[1])) == "UP2-E1005"


def test_a_field_map_holds_locals_and_drops_missing_fields() -> None:
    """A `_`-prefixed field is a local of that step: it never appears in the product."""
    story = _parse_story(
        steps=[
            {
                "name": "a",
                "parse": {
                    "_tmp": [["py", "upper", ""]],
                    "up": [["ctx", "get", "locals._tmp"]],
                    "gone": [["css1", "text", "div.nope"]],
                },
                "type": "dict",
            }
        ],
        exit="a",
    )
    assert start(story, "ab").next() == ("done", [{"up": "AB"}])


def test_a_call_argument_reference_is_resolved() -> None:
    """A `with` reference is resolved through the step's scope."""
    story = {
        "steps": [
            {"name": "a", "parse": {"u": [["py", "id", ""]]}, "type": "dict"},
            {"name": "b", "call": "host.fn", "with": {"seen": "$a.u"}, "type": "dict"},
        ],
        "exit": "b",
    }
    assert start(story, "ignored").next() == ("call", "host.fn", {"seen": "ignored"})


# ---------------------------------------------------------------- $in


def test_dollar_in_names_the_step_input() -> None:
    scope = Scope(step_input="https://x/")
    chain = [["const", "https://x/"], ["py", "==", "$in"]]
    assert eval_field(compile_field(chain), None, scope=scope) == Ok(True)


def test_dollar_in_reads_a_key_of_the_input() -> None:
    scope = Scope(step_input={"url": "https://x/"})
    chain = [["const", "https://x/"], ["py", "==", "$in.url"]]
    assert eval_field(compile_field(chain), None, scope=scope) == Ok(True)


def test_dollar_in_without_an_input_is_missing() -> None:
    outcome = eval_field(compile_field([["py", "urljoin", "$in.url"]]), "a.html", scope=Scope())
    assert isinstance(outcome, Missing)
    assert "no input was handed" in outcome.reason


def test_dollar_in_survives_a_child_scope() -> None:
    scope = Scope(step_input={"url": "https://x/"})
    chain = [["const", "https://x/"], ["py", "==", "$in.url"]]
    assert eval_field(compile_field(chain), None, scope=scope.child()) == Ok(True)


def test_the_input_root_is_reserved_but_needs_no_product() -> None:
    """`$in` compiles without declaring a product, and `in` cannot be a step name."""
    compiled = compile_field([["py", "urljoin", "$in.url"]])
    base = compiled.stages[0].params["base"]
    assert isinstance(base, Ref)
    assert base.root == "in"
    assert "in" in RESERVED_ROOTS
