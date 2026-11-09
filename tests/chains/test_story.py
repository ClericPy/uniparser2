"""The story layer: compiling a site bundle and running it (design doc 03 §2-§5).

A story is data, so every structural mistake must fail at **compile time** with a code and a JSON
Pointer; the run then only evaluates. Two things are pinned here beyond the happy path: the shape of
each effect, and the rule that an answer resumes the **same** run (no hand-off).

A step's `type` is a declared **shape** whose registry is host state (`03` §3): the fixture below
installs the two names these cases declare (`Record` / `Answer`) and puts the registry back
afterwards, so one case can never see another one's types. What a *registered constructor* really
does at the step boundary is the subject of `tests/chains/test_type_registry.py`.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from uniparser2 import (
    Failed,
    Ok,
    Ref,
    Scope,
    Up2Error,
    compile_field,
    compile_story,
    eval_field,
    register_type,
    start,
    unregister_type,
)
from uniparser2.core.refs import RESERVED_ROOTS

_DOC = "<div><a href='/p/1'>one</a><a href='/p/2'>two</a></div>"
_STORY_TYPES = ("Record", "Answer", "Page")


def _identity(*args: Any, **kwargs: Any) -> Any:
    """A stand-in host constructor: `Cls(**payload)` / `Cls(*items)` — it answers its input.

    The two names this module declares (`Record` / `Answer`) are JSON shapes here, so the stub only
    has to accept the payload; a real validating constructor is the subject of
    `tests/chains/test_type_registry.py`.
    """
    if len(args) == 1 and not kwargs:
        return args[0]
    if kwargs:
        return kwargs
    return list(args)


@pytest.fixture(autouse=True)
def _types() -> Iterator[None]:
    """The two type names these cases declare, registered only for the duration of the case."""
    for name in _STORY_TYPES:
        register_type(name, _identity)
    yield
    for name in _STORY_TYPES:
        unregister_type(name)


class Answer:
    """A stand-in host object: what an HTTP client would hand over."""

    __slots__ = ("text", "url")

    def __init__(self, text: str, url: str = "https://x/p/") -> None:
        self.text = text
        self.url = url


def _bundle(steps: list[dict[str, Any]], *, entry: str | None = None, **overrides: Any) -> Any:
    """A bundle whose entry is the first step's name, and whose exit is the last step's name.

    `entry` and `exit` are both declared keys (`03` §2), so a case that is about something else
    names them the shortest legal way and only the case under test spells them differently.
    """
    bundle: dict[str, Any] = {
        "entry": entry if entry is not None else steps[0]["name"],
        "steps": steps,
        "collect": steps[-1]["name"],
    }
    bundle.update(overrides)
    return bundle


def _parse_story(**overrides: Any) -> dict[str, Any]:
    story: dict[str, Any] = _bundle(
        [
            {
                "name": "records",
                "body": {"url": "$in", "size": [["py", "len"]]},
                "type": "Record",
            }
        ]
    )
    story.update(overrides)
    return story


def _compile_error(story: Any) -> str:
    code: str = _compile_diagnostic(story).code
    return code


def _compile_diagnostic(story: Any) -> Any:
    with pytest.raises(Up2Error) as info:
        compile_story(story)
    return info.value.diagnostic


def _run_error(story: Any, value: Any = None) -> str:
    with pytest.raises(Up2Error) as info:
        start(story, value).go()
    return info.value.diagnostic.code


# ---------------------------------------------------------------- compiling a bundle


def test_a_minimal_story_compiles() -> None:
    story = compile_story(_parse_story())
    assert [step.name for step in story.steps] == ["records"]
    assert story.entry == "records"
    assert story.collect == "records"
    assert story.steps[0].type == "Record"


def test_a_bundle_must_be_an_object() -> None:
    assert _compile_error([]) == "UP2-E1005"


def test_an_unknown_bundle_key_is_rejected() -> None:
    """`chains` is the deleted table: a parse rule is a step, so the key is gone for good."""
    code = _compile_error(_parse_story(chains={"list": [["py", "strip"]]}))
    assert code == "UP2-E1005"


def test_steps_must_be_a_non_empty_array() -> None:
    assert _compile_error({"entry": "records", "steps": [], "collect": "records"}) == "UP2-E1005"
    assert _compile_error({"entry": "records", "collect": "records"}) == "UP2-E1005"


def test_entry_is_required_and_must_resolve() -> None:
    """The start is declared, never derived from the array order (`03` §2)."""
    assert _compile_error({"steps": _parse_story()["steps"], "collect": "records"}) == "UP2-E1005"
    assert _compile_error(_parse_story(entry="nope")) == "UP2-E1016"
    assert _compile_error(_parse_story(entry=7)) == "UP2-E1005"


def test_the_run_starts_at_the_entry_not_at_the_first_step() -> None:
    """The entry is a declared name, and it must still be reachable through the flow."""
    story = _bundle(
        [
            {"name": "a", "body": {"u": [["py", "upper"]]}, "type": "dict"},
            {"name": "b", "body": {"u": [["py", "lower"]]}, "type": "dict"},
        ],
        entry="b",
    )
    assert _compile_error(story) == "UP2-E1018"
    # Making the entry the step the flow starts from runs the same array, in the same order.
    assert start(_bundle([story["steps"][0]]), "ab").go() == ("done", [{"u": "AB"}])


def test_collect_is_required_and_must_resolve() -> None:
    assert _compile_error({"entry": "records", "steps": _parse_story()["steps"]}) == "UP2-E1005"
    assert _compile_error(_parse_story(entry="records", collect="nope")) == "UP2-E1016"


def test_step_names_are_unique() -> None:
    story = _bundle(
        [
            {"name": "a", "body": {"u": "$in"}},
            {"name": "a", "body": {"u": "$in"}},
        ]
    )
    assert _compile_error(story) == "UP2-E1009"


def test_a_step_name_may_not_be_a_reserved_root() -> None:
    for reserved in RESERVED_ROOTS:
        story = _bundle([{"name": reserved, "body": {"u": "$in"}}])
        assert _compile_error(story) == "UP2-E1009"


def test_a_step_declares_exactly_one_of_parse_and_call() -> None:
    both = _bundle([{"name": "a", "body": {"u": "$in"}, "call": "host.fn"}])
    assert _compile_error(both) == "UP2-E1005"
    neither = _bundle([{"name": "a", "type": "dict"}])
    assert _compile_error(neither) == "UP2-E1005"


def test_with_belongs_to_a_call_step() -> None:
    story = _bundle([{"name": "a", "body": {"u": "$in"}, "args": {"t": 1}}])
    assert _compile_error(story) == "UP2-E1005"


def test_an_unknown_step_key_is_rejected() -> None:
    """The old `key` / `out` spellings are gone: `name` and `type` are the keys (03 §2.1)."""
    story = _bundle([{"name": "a", "body": {"u": "$in"}, "out": "dict"}])
    assert _compile_error(story) == "UP2-E1005"


def test_next_is_required_on_a_request_step() -> None:
    story = _bundle([{"name": "a", "body": {"url": "$in"}, "type": "Request"}])
    assert _compile_error(story) == "UP2-E1005"


def test_next_is_refused_on_a_step_that_produces_no_request() -> None:
    story = _bundle([{"name": "a", "body": {"u": "$in"}, "next": "a"}])
    assert _compile_error(story) == "UP2-E1005"


def test_next_must_resolve_to_a_step() -> None:
    story = _bundle([{"name": "a", "body": {"url": "$in"}, "type": "Request", "next": "gone"}])
    assert _compile_error(story) == "UP2-E1016"


def _cycle_error(story: dict[str, Any]) -> Any:
    with pytest.raises(Up2Error) as info:
        compile_story(story)
    assert info.value.diagnostic.code == "UP2-E1017"
    return info.value.diagnostic


def test_a_backward_next_that_closes_a_loop_is_rejected_at_compile_time() -> None:
    """`next` may point at any step; a loop is an authoring error the run could never finish."""
    diagnostic = _cycle_error(
        _bundle(
            [
                {
                    "name": "feed",
                    "body": {"url": "$in"},
                    "type": "Request",
                    "next": "page",
                },
                {"name": "page", "body": {"n": [["py", "len"]]}, "type": "dict"},
                {
                    "name": "again",
                    "body": {"url": "$in"},
                    "type": "Request",
                    "next": "feed",
                },
            ]
        )
    )
    # The message carries the travel path, and the pointer names the jump that closes the loop.
    assert "feed -> page -> again -> feed" in diagnostic.message
    assert diagnostic.pointer == "/steps/2/next"


def test_a_step_that_jumps_to_itself_is_a_loop() -> None:
    diagnostic = _cycle_error(
        _bundle(
            [
                {
                    "name": "bad",
                    "body": {"url": "$in"},
                    "type": "Request",
                    "next": "bad",
                }
            ]
        )
    )
    assert "bad -> bad" in diagnostic.message


def test_a_backward_next_into_a_region_that_cannot_reach_it_compiles() -> None:
    """A fan-out whose answers are parsed by a step written **earlier** is the samples' own shape.

    `fan`'s jump points backwards, but no path leads from `left` back to `fan`: the flow stays a
    chain of distinct steps, so the story compiles and runs.
    """
    story = _bundle(
        [
            {
                "name": "seed",
                "body": {"url": "$in"},
                "type": "Request",
                "next": "fan",
            },
            {
                "name": "fan",
                "body": {
                    "items": [
                        [
                            "py",
                            "const",
                            [{"url": "a", "next": "left"}, {"url": "b", "next": "right"}],
                        ]
                    ]
                },
                "type": "RequestBatch",
                "next": "left",
            },
            {"name": "left", "body": {"side": [["py", "const", "left"]]}, "type": "dict"},
            {"name": "right", "body": {"side": [["py", "const", "right"]]}, "type": "dict"},
            {"name": "joined", "body": {"n": [["py", "len"]]}, "type": "dict"},
        ]
    )
    run = start(story, "seed")
    assert run.go() == ("request", {"url": "seed"}, "fan")
    effect = run.feed(Answer("home"))
    assert effect[0] == "batch"
    assert run.feed([Answer("x"), Answer("y")]) == ("done", [{"n": 2}])


def test_a_backward_next_followed_by_a_forward_jump_compiles() -> None:
    """The books-sample shape: the region a jump enters ends forward, so the flow never loops."""
    story = _bundle(
        [
            {
                "name": "seed",
                "body": {"url": "$in"},
                "type": "Request",
                "next": "shelf_page",
            },
            {
                "name": "shelf_page",
                "body": {"page": [["py", "getattr", "text"]]},
                "type": "Page",
            },
            {
                "name": "shelf",
                "body": {
                    "items": [
                        ["py", "const", ["u"]],
                        ["each", {"url": [["py", "urljoin", "https://x/"]]}],
                    ]
                },
                "type": "RequestBatch",
                "next": "record",
            },
            {"name": "record", "body": {"body": [["py", "getattr", "text"]]}, "type": "Record"},
        ]
    )
    run = start(story, "seed")
    assert run.go() == ("request", {"url": "seed"}, "shelf_page")
    effect: Any = run.feed(Answer("list"))
    assert effect[0] == "batch"
    assert run.feed([Answer("body")]) == ("done", [{"body": "body"}])


def test_the_step_limit_is_enforced() -> None:
    steps = [{"name": f"s{index}", "body": {"u": "$in"}} for index in range(65)]
    assert _compile_error(_bundle(steps)) == "UP2-E1012"


def test_a_step_nothing_reaches_is_rejected() -> None:
    """A dead step is an authoring error, not a silently kept one (`L13`)."""
    diagnostic = _compile_diagnostic(
        _bundle(
            [
                {"name": "start", "body": {"n": [["py", "len"]]}, "type": "dict"},
                {"name": "orphan", "body": {"u": "$in"}, "type": "dict"},
            ],
            entry="orphan",
        )
    )
    assert diagnostic.code == "UP2-E1018"
    assert "start" in diagnostic.message
    assert diagnostic.pointer == "/steps/0/name"


def test_a_step_nothing_jumps_to_after_a_jump_is_rejected() -> None:
    """A `next` that skips a step leaves it dead, and the lint names it."""
    diagnostic = _compile_diagnostic(
        _bundle(
            [
                {"name": "seed", "body": {"url": "$in"}, "type": "Request", "next": "last"},
                {"name": "orphan", "body": {"u": "$in"}, "type": "dict"},
                {"name": "last", "body": {"u": "$in"}, "type": "dict"},
            ]
        )
    )
    assert diagnostic.code == "UP2-E1018"
    assert "orphan" in diagnostic.message
    assert diagnostic.pointer == "/steps/1/name"


def test_an_entry_that_is_not_the_first_step_leaves_the_earlier_one_unreachable() -> None:
    story = _bundle(
        [
            {"name": "dead", "body": {"u": "$in"}, "type": "dict"},
            {"name": "live", "body": {"u": "$in"}, "type": "dict"},
        ],
        entry="live",
    )
    diagnostic = _compile_diagnostic(story)
    assert diagnostic.code == "UP2-E1018"
    assert "dead" in diagnostic.message


def test_every_step_of_a_linear_story_is_reachable() -> None:
    story = _bundle(
        [
            {"name": "a", "body": {"u": "$in"}, "type": "dict"},
            {"name": "b", "body": {"u": "$in"}, "type": "dict"},
            {"name": "c", "body": {"u": "$in"}, "type": "dict"},
        ]
    )
    assert [step.name for step in compile_story(story).steps] == ["a", "b", "c"]


def test_an_empty_field_map_is_rejected() -> None:
    story = _bundle([{"name": "a", "body": {}, "type": "dict"}])
    assert _compile_error(story) == "UP2-E1005"


# ---------------------------------------------------------------- running a story


def test_a_story_without_requests_finishes_at_once() -> None:
    run = start(_parse_story(), "u")
    assert run.go() == ("done", [{"url": "u", "size": 1}])


def test_done_is_idempotent_and_send_is_refused() -> None:
    run = start(_parse_story(), "u")
    assert run.go()[0] == "done"
    assert run.go() == run.go()
    with pytest.raises(ValueError, match="already done"):
        run.feed("anything")


def test_a_request_suspends_the_run() -> None:
    story = _bundle(
        [
            {
                "name": "seed",
                "body": {"url": "$in"},
                "type": "Request",
                "next": "records",
            },
            {"name": "records", "body": {"body": [["py", "getattr", "text"]]}, "type": "Record"},
        ]
    )
    run = start(story, "https://x/list.html")
    assert run.go() == ("request", {"url": "https://x/list.html"}, "records")
    answer = Answer(_DOC)
    assert run.feed(answer) == ("done", [{"body": _DOC}])
    assert run.go() == ("done", [{"body": _DOC}])


def test_the_answer_is_never_copied_or_converted() -> None:
    """The receiving step reads the host's own object: `$in` and `getattr` see the same instance."""
    story = _bundle(
        [
            {
                "name": "seed",
                "body": {"url": "$in"},
                "type": "Request",
                "next": "read",
            },
            {
                "name": "read",
                "body": {
                    "final": [["py", "getattr", "url"]],
                    "resolved": [["py", "const", "https://x/final"], ["py", "==", "$in.url"]],
                },
                "type": "Answer",
            },
        ]
    )
    answer = Answer(_DOC, url="https://x/final")
    run = start(story, "https://x/list.html")
    run.go()
    # `$in.url` resolved against the host's own object: the receiving step's input is that object.
    assert run.feed(answer) == ("done", [{"final": "https://x/final", "resolved": True}])


def test_a_step_product_that_is_not_json_stops_the_run() -> None:
    """A value may flow, but a step product must be JSON (03 §3.3, UP2-E2003)."""
    story = _bundle(
        [
            {
                "name": "seed",
                "body": {"url": "$in"},
                "type": "Request",
                "next": "keep",
            },
            {"name": "keep", "body": "$in", "type": "Answer"},
        ]
    )
    run = start(story, "seed")
    run.go()
    with pytest.raises(Up2Error) as info:
        run.feed(Answer(_DOC))
    assert info.value.diagnostic.code == "UP2-E2003"


def test_a_batch_runs_the_receiving_step_once_per_answer_and_rejoins() -> None:
    story = _bundle(
        [
            {
                "name": "seed",
                "body": {"url": "$in"},
                "type": "Request",
                "next": "fan",
            },
            {
                "name": "fan",
                "body": {"items": [["py", "const", [{"url": "a"}, {"url": "b"}]]]},
                "type": "RequestBatch",
                "next": "page",
            },
            {"name": "page", "body": [["py", "getattr", "text"]], "type": "Page"},
            {"name": "count", "body": {"n": [["py", "len"]]}, "type": "dict"},
        ]
    )
    run = start(story, "seed")
    assert run.go() == ("request", {"url": "seed"}, "fan")
    effect = run.feed(Answer("seed page"))
    assert effect == ("batch", [{"url": "a"}, {"url": "b"}], "page")
    assert run.feed([Answer("a page"), Answer("b page")]) == ("done", [{"n": 2}])


def test_a_task_may_override_next() -> None:
    story = _bundle(
        [
            {
                "name": "seed",
                "body": {"url": "$in"},
                "type": "Request",
                "next": "fan",
            },
            {
                "name": "fan",
                "body": {
                    "items": [
                        [
                            "py",
                            "const",
                            [{"url": "a", "next": "left"}, {"url": "b", "next": "right"}],
                        ]
                    ]
                },
                "type": "RequestBatch",
                "next": "left",
            },
            {"name": "left", "body": {"side": [["py", "const", "left"]]}, "type": "dict"},
            {"name": "right", "body": {"side": [["py", "const", "right"]]}, "type": "dict"},
            {"name": "joined", "body": {"n": [["py", "len"]]}, "type": "dict"},
        ]
    )
    run = start(story, "seed")
    run.go()
    effect = run.feed(Answer("home"))
    assert effect == ("batch", [{"url": "a"}, {"url": "b"}], "left")
    # The host never sees `next`: it is the kernel's routing key. The tuple's second slot is a union
    # of every effect shape, so it goes through an explicitly typed variable (the device
    # ``tests/core/test_core_edges.py`` uses for a deliberate ``Any``).
    batch: Any = effect[1]
    assert all("next" not in task for task in batch)
    # The first task routes left, the second right; both products join and continue after `left`.
    assert run.feed([Answer("x"), Answer("y")]) == ("done", [{"n": 2}])


def test_a_task_next_may_be_a_plain_string() -> None:
    """A task's `next` is a step name, so the plain string is the value itself (`03` §4.1.1).

    It is the same writing the step-level `next` uses; the chain form stays available for a target
    a fan-out computes from the item's own data.
    """
    story = _bundle(
        [
            {
                "name": "seed",
                "body": {"url": "$in"},
                "type": "Request",
                "next": "fan",
            },
            {
                "name": "fan",
                "body": {
                    "items": [
                        [
                            "py",
                            "const",
                            [{"url": "a", "next": "left"}, {"url": "b", "next": "right"}],
                        ]
                    ]
                },
                "type": "RequestBatch",
                "next": "left",
            },
            {"name": "left", "body": {"side": [["py", "const", "left"]]}, "type": "dict"},
            {"name": "right", "body": {"side": [["py", "const", "right"]]}, "type": "dict"},
            {"name": "joined", "body": {"n": [["py", "len"]]}, "type": "dict"},
        ]
    )
    run = start(story, "seed")
    run.go()
    effect = run.feed(Answer("home"))
    # The task's own string overrides the step's default, exactly as the chain form did.
    assert effect == ("batch", [{"url": "a"}, {"url": "b"}], "left")
    assert run.feed([Answer("x"), Answer("y")]) == ("done", [{"n": 2}])


def test_a_task_string_next_that_names_nothing_is_e1016() -> None:
    story = _bundle(
        [
            {
                "name": "seed",
                "body": {"url": "$in"},
                "type": "Request",
                "next": "fan",
            },
            {
                "name": "fan",
                "body": {"items": [["py", "const", [{"url": "a", "next": "gone"}]]]},
                "type": "RequestBatch",
                "next": "sink",
            },
            {"name": "sink", "body": {"seen": "$in"}, "type": "dict"},
        ]
    )
    run = start(story, "seed")
    run.go()
    with pytest.raises(Up2Error) as info:
        run.feed(Answer("home"))
    assert info.value.diagnostic.code == "UP2-E1016"


def test_a_receiving_step_may_itself_produce_a_request() -> None:
    story = _bundle(
        [
            {
                "name": "seed",
                "body": {"url": "$in"},
                "type": "Request",
                "next": "gather",
            },
            {
                "name": "gather",
                "body": {"items": [["py", "const", [{"url": "a"}]]]},
                "type": "RequestBatch",
                "next": "page",
            },
            {
                "name": "page",
                "body": {"url": [["py", "getattr", "url"]]},
                "type": "Request",
                "next": "record",
            },
            {"name": "record", "body": {"body": [["py", "getattr", "text"]]}, "type": "Record"},
        ]
    )
    run = start(story, "seed")
    run.go()
    assert run.feed(Answer("home"))[0] == "batch"
    # The receiving step is itself a request: the run suspends again, inside the same fan-out.
    assert run.feed([Answer("page 1")]) == (
        "request",
        {"url": "https://x/p/"},
        "record",
    )
    assert run.feed(Answer("record body")) == ("done", [{"body": "record body"}])


def test_a_call_suspends_and_resumes_with_the_receipt() -> None:
    story = _bundle(
        [
            {"name": "records", "body": {"url": "$in"}, "type": "Record"},
            {
                "name": "store",
                "call": "host.store_records",
                "args": {"table": "records", "from": "$records.url"},
                "type": "dict",
            },
        ]
    )
    run = start(story, "u")
    assert run.go() == ("call", "host.store_records", {"table": "records", "from": "u"})
    assert run.feed({"stored": 1}) == ("done", [{"stored": 1}])


def test_a_collect_step_that_matched_nothing_still_contributes() -> None:
    """A no-match is a value: the exit step contributes its product, never a skipped step."""
    story = _bundle(
        [
            {
                "name": "seed",
                "body": {"url": "$in"},
                "type": "Request",
                "next": "record",
            },
            {"name": "record", "body": [["py", "getattr", "text"], ["css1", "text", "div.nope"]]},
            {"name": "backup", "body": {"seen": [["py", "const", "backup"]]}, "type": "dict"},
        ],
        entry="seed",
        collect="record",
    )
    run = start(story, "seed")
    assert run.go() == ("request", {"url": "seed"}, "record")
    assert run.feed(Answer("home")) == ("done", [""])


def test_a_failing_step_stops_the_run_with_its_code() -> None:
    story = _bundle([{"name": "bad", "body": [["py", "int"]], "type": "int"}])
    assert _run_error(story, "not-a-number") == "UP2-E2005"
    with pytest.raises(Up2Error) as info:
        start(story, "not-a-number").go()
    assert info.value.diagnostic.pointer == "/steps/0"


def test_a_chain_that_matched_nothing_produces_the_empty_value() -> None:
    """A selector that matched nothing yields `""`, and the step still contributes a product."""
    story = _bundle([{"name": "a", "body": [["css1", "text", "div.nope"]]}])
    assert start(story, _DOC).go() == ("done", [""])


def test_an_unreadable_reference_stops_the_run() -> None:
    """A path that does not exist is a failure (`UP2-E2001`), so a later step cannot rely on it."""
    story = _bundle(
        [
            {"name": "gone", "body": [["css1", "text", "div.nope"]]},
            {"name": "later", "body": {"u": [["ctx", "get", "locals.nope"], ["py", "strip"]]}},
        ]
    )
    assert _run_error(story, _DOC) == "UP2-E2001"


def test_a_receiving_step_produces_the_empty_value_and_the_run_continues() -> None:
    """A receiving step whose chain matched nothing produces `""`; the run continues after it."""
    story = _bundle(
        [
            {
                "name": "seed",
                "body": {"url": "$in"},
                "type": "Request",
                "next": "read",
            },
            # `css1` matches nothing in the answer text, so this step produces no product at all.
            {"name": "read", "body": [["css1", "text", "div.nope"]], "type": "Record"},
            {"name": "after", "body": {"seen": [["py", "const", "after"]]}, "type": "dict"},
        ]
    )
    run = start(story, "https://x/list.html")
    assert run.go() == ("request", {"url": "https://x/list.html"}, "read")
    # `read` produced nothing, so the run goes on at the step after it — not at a null product.
    assert run.feed(_DOC) == ("done", [{"seen": "after"}])


def test_a_batch_answer_of_the_wrong_size_is_a_host_error() -> None:
    story = _bundle(
        [
            {
                "name": "seed",
                "body": {"url": "$in"},
                "type": "Request",
                "next": "fan",
            },
            {
                "name": "fan",
                "body": {"items": [["py", "const", [{"url": "a"}, {"url": "b"}]]]},
                "type": "RequestBatch",
                "next": "page",
            },
            {"name": "page", "body": [["py", "getattr", "text"]], "type": "Page"},
        ]
    )
    run = start(story, "seed")
    run.go()
    run.feed(Answer("home"))
    with pytest.raises(ValueError, match="2 answers"):
        run.feed([Answer("only one")])


def test_a_batch_product_without_items_is_a_story_error() -> None:
    story = _bundle(
        [
            {
                "name": "bad",
                "body": {"nope": [["py", "len"]]},
                "type": "RequestBatch",
                "next": "sink",
            },
            {"name": "sink", "body": {"seen": "$in"}, "type": "dict"},
        ],
        collect="bad",
    )
    assert _run_error(story, {"a": 1}) == "UP2-E2005"


def test_a_task_routing_to_an_unknown_step_fails() -> None:
    """A task's own `next` is data, so its target is checked when the batch is handed over."""
    story = _bundle(
        [
            {
                "name": "seed",
                "body": {"url": "$in"},
                "type": "Request",
                "next": "fan",
            },
            {
                "name": "fan",
                "body": {"items": [["py", "const", [{"url": "a", "next": "gone"}]]]},
                "type": "RequestBatch",
                "next": "sink",
            },
            {"name": "sink", "body": {"seen": "$in"}, "type": "dict"},
        ],
        collect="fan",
    )
    run = start(story, "seed")
    run.go()
    with pytest.raises(Up2Error) as info:
        run.feed(Answer("home"))
    assert info.value.diagnostic.code == "UP2-E1016"


def test_a_request_product_that_is_not_an_object_is_a_story_error() -> None:
    story = _bundle(
        [
            {"name": "bad", "body": [["py", "const", 7]], "type": "Request", "next": "sink"},
            {"name": "sink", "body": {"seen": "$in"}, "type": "dict"},
        ],
        collect="bad",
    )
    assert _run_error(story, "ignored") == "UP2-E2005"


def test_a_batch_task_that_is_not_an_object_is_a_story_error() -> None:
    story = _bundle(
        [
            {
                "name": "bad",
                "body": {"items": [["py", "const", [7]]]},
                "type": "RequestBatch",
                "next": "sink",
            },
            {"name": "sink", "body": {"seen": "$in"}, "type": "dict"},
        ],
        collect="bad",
    )
    assert _run_error(story, "ignored") == "UP2-E2005"


def test_the_run_exposes_its_story_and_input_and_can_be_closed() -> None:
    run = start(_parse_story(), "u")
    assert run.story.entry == "records"
    assert run.story.collect == "records"
    assert run.value == "u"
    run.close()


def test_a_step_must_be_an_object() -> None:
    assert _compile_error({"entry": "records", "steps": [7], "collect": "records"}) == "UP2-E1005"


def test_a_step_with_a_non_string_call_is_rejected() -> None:
    assert _compile_error(_bundle([{"name": "a", "call": 7}])) == "UP2-E1005"


def test_a_globals_table_must_be_an_object() -> None:
    assert _compile_error(_parse_story(globals=[1])) == "UP2-E1005"


def test_a_field_map_holds_locals_and_keeps_empty_fields() -> None:
    """A `_`-prefixed field is a local of that step: it never appears in the product."""
    story = _bundle(
        [
            {
                "name": "a",
                "body": {
                    "_tmp": [["py", "upper"]],
                    "up": [["ctx", "get", "locals._tmp"]],
                    "gone": [["css1", "text", "div.nope"]],
                },
                "type": "dict",
            }
        ]
    )
    assert start(story, "ab").go() == ("done", [{"up": "AB", "gone": ""}])


def test_a_call_argument_reference_is_resolved() -> None:
    """A `with` reference is resolved through the step's scope."""
    story = _bundle(
        [
            {"name": "a", "body": {"u": "$in"}, "type": "dict"},
            {"name": "b", "call": "host.fn", "args": {"seen": "$a.u"}, "type": "dict"},
        ]
    )
    assert start(story, "ignored").go() == ("call", "host.fn", {"seen": "ignored"})


def test_obj_is_not_readable_in_a_call_argument() -> None:
    """``$obj`` names a stage's value; a call step's arguments are not a stage (design D11)."""
    story = _bundle(
        [
            {"name": "a", "body": {"u": "$in"}, "type": "dict"},
            {"name": "b", "call": "host.fn", "args": {"seen": "$obj"}, "type": "dict"},
        ]
    )
    assert _run_error(story, "ignored") == "UP2-E2001"


# ---------------------------------------------------------------- a whole-chain reference


def test_a_chain_may_be_a_whole_chain_reference() -> None:
    """`$` in chain position is the value the reference names, unchanged (`03` §2)."""
    story = _bundle(
        [
            {"name": "a", "body": {"out": "$in"}, "type": "dict"},
        ]
    )
    assert start(story, "  not stripped  ").go() == ("done", [{"out": "  not stripped  "}])


def test_a_step_parse_may_be_a_whole_chain_reference() -> None:
    story = _bundle([{"name": "a", "body": "$in", "type": "dict"}])
    assert start(story, {"k": 1}).go() == ("done", [{"k": 1}])


def test_a_chain_reference_leaves_its_value_unconverted() -> None:
    """The reference is not a conversion: a host object stays the object it named."""
    answer = Answer(_DOC, url="https://x/final")
    story = _bundle(
        [
            {"name": "seed", "body": {"url": "$in"}, "type": "Request", "next": "read"},
            {"name": "read", "body": {"url": ["$in", ["py", "getattr", "url"]]}, "type": "dict"},
        ]
    )
    run = start(story, "seed")
    run.go()
    # `$in` handed the answer object on as it is, so `getattr` reads its own attribute.
    assert run.feed(answer) == ("done", [{"url": "https://x/final"}])


def test_a_chain_reference_is_not_converted_by_the_next_stage() -> None:
    """`$in` inside an `each` field map names the **step's** input, not the element (`02` §5).

    The element is the chain's *input value*, which is what the stage above consumes -- so a field
    that wants the element writes the stage, exactly as it does anywhere else in a field map.
    """
    story = _bundle(
        [
            {
                "name": "a",
                "body": {
                    "items": [
                        ["py", "const", ["x", "y"]],
                        ["each", {"elem": [["py", "upper"]], "whole": "$in"}],
                    ],
                },
                "type": "dict",
            }
        ]
    )
    outcome = start(story, {"seed": "s"}).go()
    assert outcome[0] == "done"
    assert outcome[1] == [
        {
            "items": [
                {"elem": "X", "whole": {"seed": "s"}},
                {"elem": "Y", "whole": {"seed": "s"}},
            ]
        }
    ]


def test_a_chain_reference_reads_a_step_product() -> None:
    story = _bundle(
        [
            {"name": "a", "body": {"u": [["py", "upper"]]}, "type": "dict"},
            {"name": "b", "body": {"seen": "$a.u"}, "type": "dict"},
        ]
    )
    assert start(story, "ab").go() == ("done", [{"seen": "AB"}])


def test_a_chain_that_opens_with_a_reference_reads_a_key_of_the_step_input() -> None:
    story = _bundle(
        [
            {
                "name": "a",
                "body": {"u": ["$in", ["py", "getitem", "url"]]},
                "type": "dict",
            }
        ]
    )
    assert start(story, {"url": "https://x/"}).go() == ("done", [{"u": "https://x/"}])


def test_a_chain_reference_to_an_unknown_root_is_rejected() -> None:
    story = _bundle([{"name": "a", "body": {"u": "$nope"}}])
    assert _compile_error(story) == "UP2-E1006"


def test_the_retired_fields_root_is_rejected() -> None:
    """`$fields` was a second name for `$locals` and is gone: it is an unknown root."""
    story = _bundle([{"name": "a", "body": {"u": "$fields.title"}}])
    assert _compile_error(story) == "UP2-E1006"


def test_a_chain_reference_to_its_own_step_is_rejected() -> None:
    story = _bundle([{"name": "rows", "body": {"url": "$rows.url"}}])
    assert _compile_error(story) == "UP2-E1006"


def test_a_chain_reference_to_a_local_of_another_step_is_rejected() -> None:
    story = _bundle(
        [
            {"name": "a", "body": {"_tmp": [["py", "strip"]]}},
            {"name": "b", "body": {"u": "$a._tmp"}},
        ]
    )
    assert _compile_error(story) == "UP2-E1014"


# ---------------------------------------------------------------- $in


def test_dollar_in_names_the_step_input() -> None:
    scope = Scope(step_input="https://x/")
    chain = [["py", "const", "https://x/"], ["py", "==", "$in"]]
    assert eval_field(compile_field(chain), None, scope=scope) == Ok(True)


def test_dollar_in_reads_a_key_of_the_input() -> None:
    scope = Scope(step_input={"url": "https://x/"})
    chain = [["py", "const", "https://x/"], ["py", "==", "$in.url"]]
    assert eval_field(compile_field(chain), None, scope=scope) == Ok(True)


def test_dollar_in_without_an_input_fails() -> None:
    outcome = eval_field(compile_field([["py", "urljoin", "$in.url"]]), "a.html", scope=Scope())
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2001"
    assert "no input was handed" in outcome.reason


def test_dollar_in_survives_a_child_scope() -> None:
    scope = Scope(step_input={"url": "https://x/"})
    chain = [["py", "const", "https://x/"], ["py", "==", "$in.url"]]
    assert eval_field(compile_field(chain), None, scope=scope.child()) == Ok(True)


def test_the_input_root_is_reserved_but_needs_no_product() -> None:
    """`$in` compiles without declaring a product, and `in` cannot be a step name."""
    compiled = compile_field([["py", "urljoin", "$in.url"]])
    base = compiled.stages[0].params["base"]
    assert isinstance(base, Ref)
    assert base.root == "in"
    assert "in" in RESERVED_ROOTS
