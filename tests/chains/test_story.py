"""The story layer: a story is a map of callable nodes (design doc 03 §2-§5).

A story is data, so every structural mistake fails at **compile time** with a code and a JSON
Pointer; the run only evaluates. The cases pin the node model: a node is a chain or a field map,
`["node", …]` calls it, every field map result lands in `$locals`, `["type", …]` validates the tail,
and `run` is the synchronous facade.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from uniparser2 import (
    Trace,
    Up2Error,
    compile_story,
    register_type,
    run,
    unregister_type,
)
from uniparser2.core.refs import RESERVED_ROOTS

_STORY_TYPES = ("Article", "BadShape")


class _Response:
    """A stand-in host object: what an HTTP client would hand over."""

    __slots__ = ("status_code", "text", "url")

    def __init__(self, text: str, url: str = "https://x/p/", status_code: int = 200) -> None:
        self.text = text
        self.url = url
        self.status_code = status_code


@dataclass
class _Article:
    url: str
    title: str
    pub_time: str = ""


def _bad_shape(**payload: Any) -> Any:
    del payload
    return {1, 2}


@pytest.fixture(autouse=True)
def _types() -> Iterator[None]:
    register_type("Article", _Article)
    register_type("BadShape", _bad_shape)
    yield
    for name in _STORY_TYPES:
        unregister_type(name)


def _story(nodes: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    bundle: dict[str, Any] = {"nodes": nodes}
    bundle.update(overrides)
    return bundle


def _compile_error(story: Any) -> Any:
    with pytest.raises(Up2Error) as info:
        compile_story(story)
    return info.value.diagnostic


def _run_error(story: Any, *args: Any, **kwargs: Any) -> Any:
    with pytest.raises(Up2Error) as info:
        run(story, *args, **kwargs)
    return info.value.diagnostic


# ---------------------------------------------------------------- compiling a story


def test_a_minimal_story_compiles() -> None:
    story = compile_story(_story({"parse": [["py", "strip"]]}))
    assert tuple(story.nodes) == ("parse",)
    assert story.globals == {}


def test_a_bundle_must_be_an_object() -> None:
    assert _compile_error([]).code == "UP2-E1005"


def test_the_old_keys_are_rejected() -> None:
    for key in ("entry", "collect", "steps"):
        assert _compile_error(_story({}, **{key: "x"})).code == "UP2-E1005"


def test_nodes_must_be_a_non_empty_object() -> None:
    assert _compile_error({"nodes": {}}).code == "UP2-E1005"
    assert _compile_error({"nodes": []}).code == "UP2-E1005"
    assert _compile_error({}).code == "UP2-E1005"


def test_globals_must_be_an_object() -> None:
    assert _compile_error(_story({"a": []}, globals=[1])).code == "UP2-E1005"


def test_a_node_must_be_a_chain_or_a_field_map() -> None:
    for body in ("$in", 7, None, True):
        assert _compile_error(_story({"bad": body})).code == "UP2-E1005"


def test_an_empty_field_map_is_rejected() -> None:
    assert _compile_error(_story({"bad": {}})).code == "UP2-E1005"


def test_an_empty_chain_is_identity() -> None:
    assert run(_story({"a": []}), "a", "x") == "x"


def test_a_field_may_be_identity() -> None:
    story = _story({"a": {"same": []}})
    assert run(story, "a", {"k": 1}) == {"same": {"k": 1}}


def test_node_names_are_validated() -> None:
    for name in RESERVED_ROOTS:
        assert _compile_error(_story({name: []})).code == "UP2-E1009"
    for name in ("a.b", "a/b", "a~b", ""):
        assert _compile_error(_story({name: []})).code == "UP2-E1009"


def test_the_node_limit_is_enforced() -> None:
    nodes: dict[str, Any] = {f"n{index}": [] for index in range(65)}
    assert _compile_error(_story(nodes)).code == "UP2-E1012"


# ---------------------------------------------------------------- node bodies


def test_a_chain_runs_once_on_the_node_input() -> None:
    story = _story({"a": [["py", "strip"], ["py", "upper"]]})
    assert run(story, "a", "  x  ") == "X"


def test_a_field_map_runs_every_field_on_the_node_input() -> None:
    story = _story({"a": {"up": [["py", "upper"]], "low": [["py", "lower"]]}})
    assert run(story, "a", "X") == {"up": "X", "low": "x"}


def test_every_field_is_a_local() -> None:
    story = _story({"a": {"title": [["py", "strip"]], "seen": [["ctx", "get", "locals.title"]]}})
    assert run(story, "a", "  x  ") == {"title": "x", "seen": "x"}


def test_an_underscore_field_stays_out_of_the_product() -> None:
    story = _story(
        {
            "a": {
                "_t": [["py", "strip"]],
                "seen": [["ctx", "get", "locals._t"]],
            }
        }
    )
    assert run(story, "a", " x ") == {"seen": "x"}


def test_a_field_chain_sees_the_node_input_not_the_previous_field() -> None:
    story = _story({"a": {"a": [["py", "upper"]], "b": [["py", "lower"]]}})
    assert run(story, "a", "x") == {"a": "X", "b": "x"}


# ---------------------------------------------------------------- node calls


def test_a_node_call_composes_two_chains() -> None:
    story = _story({"a": [["py", "upper"], ["node", "b"]], "b": [["py", "strip"]]})
    assert run(story, "a", " x ") == "X"


def test_the_callee_sees_the_call_value() -> None:
    story = _story({"a": [["py", "const", "v"], ["node", "b"]], "b": {"seen": []}})
    assert run(story, "a") == {"seen": "v"}


def test_a_callee_sees_the_callers_locals() -> None:
    story = _story(
        {
            "a": [["py", "strip"], ["ctx", "set", "locals._t"], ["node", "b"]],
            "b": {"seen": [["ctx", "get", "locals._t"]]},
        }
    )
    assert run(story, "a", " x ") == {"seen": "x"}


def test_a_node_call_restores_the_callers_dollar_in() -> None:
    story = _story(
        {
            "a": [["py", "const", "outer"], ["node", "b"], ["py", "==", "$in"]],
            "b": [["py", "const", "inner"]],
        }
    )
    # The value at the comparison is "inner"; `$in` is still the caller's "outer".
    assert run(story, "a", "outer") is False


def test_a_node_call_inside_each_runs_once_per_element() -> None:
    story = _story(
        {
            "top": [["py", "const", [{"u": 1}, {"u": 2}]], ["each", [["node", "detail"]]]],
            "detail": {"u": [["py", "getitem", "u"]]},
        }
    )
    assert run(story, "top") == [{"u": 1}, {"u": 2}]


def test_an_unknown_node_is_rejected_at_compile_time() -> None:
    diagnostic = _compile_error(_story({"a": [["node", "gone"]]}))
    assert diagnostic.code == "UP2-E1016"
    assert "gone" in diagnostic.message


def test_a_node_stage_has_two_slots() -> None:
    assert _compile_error(_story({"a": [["node", "a", "extra"]], "b": []})).code == "UP2-E1004"


def test_a_standalone_chain_cannot_call_a_node() -> None:
    from uniparser2 import compile_field

    with pytest.raises(Up2Error) as info:
        compile_field([["node", "x"]])
    assert info.value.diagnostic.code == "UP2-E1016"


def test_a_direct_self_call_is_a_cycle() -> None:
    assert _compile_error(_story({"a": [["node", "a"]]})).code == "UP2-E1017"


def test_an_indirect_cycle_is_a_cycle() -> None:
    diagnostic = _compile_error(_story({"a": [["node", "b"]], "b": [["node", "a"]]}))
    assert diagnostic.code == "UP2-E1017"
    assert "a -> b -> a" in diagnostic.message
    assert diagnostic.pointer == "/nodes/b/0"


def test_a_cycle_inside_a_field_map_points_at_the_stage() -> None:
    diagnostic = _compile_error(_story({"a": [["node", "b"]], "b": {"x": [["node", "a"]]}}))
    assert diagnostic.code == "UP2-E1017"
    assert diagnostic.pointer == "/nodes/b/x/0"


def test_a_cycle_through_an_each_subchain_is_a_cycle() -> None:
    story = _story({"a": [["each", [["node", "a"]]]]})
    assert _compile_error(story).code == "UP2-E1017"


# ---------------------------------------------------------------- each and $in


def test_dollar_in_inside_each_is_the_node_input() -> None:
    story = _story(
        {
            "a": [
                ["py", "const", ["x", "y"]],
                ["each", {"elem": [["py", "upper"]], "eq": [["py", "==", "$in"]]}],
            ]
        }
    )
    # `$in` is the node input `"seed"`, not the element, so every comparison is false.
    assert run(story, "a", "seed") == [
        {"elem": "X", "eq": False},
        {"elem": "Y", "eq": False},
    ]


def test_each_field_values_are_locals_of_the_element() -> None:
    story = _story(
        {
            "a": [
                ["py", "const", [" x "]],
                ["each", {"raw": [["py", "strip"]], "seen": [["ctx", "get", "locals.raw"]]}],
            ]
        }
    )
    assert run(story, "a") == [{"raw": "x", "seen": "x"}]


def test_an_element_local_does_not_leak_to_the_next_element() -> None:
    story = _story(
        {
            "a": [
                ["py", "const", ["a", "b"]],
                ["each", {"_t": [["py", "upper"]], "seen": [["ctx", "get", "locals._t"]]}],
            ]
        }
    )
    assert run(story, "a") == [{"seen": "A"}, {"seen": "B"}]


# ---------------------------------------------------------------- types


def test_a_type_stage_constructs_the_declared_type() -> None:
    story = _story(
        {
            "a": [
                ["py", "const", {"url": "u", "title": "t"}],
                ["type", "Article"],
                ["py", "getattr", "title"],
            ]
        }
    )
    assert run(story, "a") == "t"


def test_a_type_stage_reports_a_missing_key() -> None:
    story = _story({"a": [["py", "const", {"url": "u"}], ["type", "Article"]]})
    diagnostic = _run_error(story, "a")
    assert diagnostic.code == "UP2-E2019"
    assert "title" in diagnostic.message


def test_an_unregistered_type_is_e1011() -> None:
    story = _story({"a": [["py", "const", {}], ["type", "Gone"]]})
    assert _run_error(story, "a").code == "UP2-E1011"


def test_a_non_json_type_answer_is_e2003() -> None:
    story = _story({"a": [["py", "const", {"url": "u"}], ["type", "BadShape"]]})
    assert _run_error(story, "a").code == "UP2-E2003"


def test_a_type_stage_may_be_followed_by_another_stage() -> None:
    """`type` is a constructor stage, not a chain tail: a stage after it reads the instance."""
    story = _story(
        {
            "a": [
                ["py", "const", {"url": "u", "title": "t"}],
                ["type", "Article"],
                ["py", "getattr", "url"],
            ]
        }
    )
    assert run(story, "a") == "u"


def test_a_field_map_node_can_be_wrapped_by_a_type_node() -> None:
    story = _story(
        {
            "a": [["node", "fields"], ["type", "Article"], ["py", "getattr", "title"]],
            "fields": {"url": [["py", "const", "u"]], "title": [["py", "const", "t"]]},
        }
    )
    assert run(story, "a") == "t"


# ---------------------------------------------------------------- udf


def test_udf_receives_the_upstream_value_as_one_dto() -> None:
    seen: list[Any] = []

    def f(value: Any) -> Any:
        seen.append(value)
        return {"got": value}

    story = _story({"a": [["py", "const", {"x": 1}], ["udf", "f"]]})
    assert run(story, "a", udfs={"f": f}) == {"got": {"x": 1}}
    assert seen == [{"x": 1}]


def test_udf_spreads_a_list_with_star() -> None:
    def f(*args: Any) -> Any:
        return list(args)

    story = _story({"a": [["py", "const", [1, 2]], ["udf", "f", "*"]]})
    assert run(story, "a", udfs={"f": f}) == [1, 2]


def test_udf_spreads_a_mapping_with_double_star() -> None:
    def f(**kwargs: Any) -> Any:
        return kwargs

    story = _story({"a": [["py", "const", {"a": 1}], ["udf", "f", "**"]]})
    assert run(story, "a", udfs={"f": f}) == {"a": 1}


def test_udf_takes_one_explicit_argument() -> None:
    story = _story({"a": [["udf", "f", "x"]]})
    assert run(story, "a", udfs={"f": lambda value: value}) == "x"


def test_a_missing_udf_is_reported_before_evaluation() -> None:
    story = _story({"a": [["udf", "fetch"]]})
    diagnostic = _run_error(story, "a")
    assert diagnostic.code == "UP2-E1010"
    assert "fetch" in diagnostic.message


def test_only_the_reachable_nodes_udfs_are_required() -> None:
    """A sibling node may fetch; running the ETL node must not require `fetch`."""
    story = _story({"etl": [["py", "strip"]], "fetchy": [["udf", "fetch"]]})
    assert run(story, "etl", " x ") == "x"
    assert _run_error(story, "fetchy").code == "UP2-E1010"


def test_a_udf_may_return_a_host_object_mid_chain() -> None:
    story = _story({"a": [["udf", "respond"], ["py", "getattr", "text"]]})
    assert run(story, "a", udfs={"respond": lambda value: _Response("body")}) == "body"


def test_a_host_object_cannot_be_the_exit() -> None:
    story = _story({"a": [["udf", "respond"]]})
    assert _run_error(story, "a", udfs={"respond": lambda value: _Response("body")}).code == (
        "UP2-E2003"
    )


def test_an_awaitable_udf_answer_is_e2009() -> None:
    async def f(value: Any) -> Any:
        return value

    story = _story({"a": [["udf", "f"]]})
    diagnostic = _run_error(story, "a", udfs={"f": f})
    assert diagnostic.code == "UP2-E2009"


def test_the_fetch_shape_runs_offline() -> None:
    """The target flow: list -> each -> fetch -> read the response."""

    def fetch(value: Any) -> Any:
        return _Response(f"body:{value['url']}", url=str(value["url"]), status_code=201)

    story = _story(
        {
            "top": [
                ["py", "const", ["https://x/1", "https://x/2"]],
                [
                    "each",
                    [
                        ["ctx", "dict", {"url": "obj"}],
                        ["udf", "fetch"],
                        ["py", "getattr", "status_code"],
                    ],
                ],
            ],
        }
    )
    assert run(story, "top", udfs={"fetch": fetch}) == [201, 201]


# ---------------------------------------------------------------- run


def test_the_first_node_is_the_default_entry() -> None:
    story = _story({"a": [["py", "upper"]], "b": [["py", "lower"]]})
    assert run(story, input="x") == "X"


def test_a_named_node_runs() -> None:
    story = _story({"a": [["py", "upper"]], "b": [["py", "lower"]]})
    assert run(story, "b", "X") == "x"


def test_globals_override_for_one_run() -> None:
    story = _story(
        {"a": [["py", "urljoin", "$globals.base_url"]]},
        globals={"base_url": "https://story/"},
    )
    assert run(story, "a", "p", globals={"base_url": "https://run/"}) == "https://run/p"
    assert run(story, "a", "p") == "https://story/p"


def test_run_udfs_overlay_the_process_wide_table() -> None:
    story = _story({"a": [["udf", "f"]]})
    assert run(story, "a", udfs={"f": lambda value: "local"}) == "local"


def test_an_unknown_node_name_is_e1016() -> None:
    story = _story({"a": []})
    assert _run_error(story, "gone").code == "UP2-E1016"


def test_a_failing_stage_reports_the_node_pointer() -> None:
    story = _story({"bad": [["py", "int"]]})
    diagnostic = _run_error(story, "bad", "not-a-number")
    assert diagnostic.code == "UP2-E2005"
    assert diagnostic.pointer == "/nodes/bad"


def test_the_trace_names_the_node_and_field() -> None:
    trace = Trace()
    story = _story({"a": {"title": [["py", "strip"]]}})
    assert run(story, "a", " x ", trace=trace) == {"title": "x"}
    events = trace.events
    assert events[-1].node == "a"
    assert events[-1].field == "title"


def test_a_chain_must_still_be_an_array() -> None:
    story = _story({"a": "$in"})
    assert _compile_error(story).code == "UP2-E1005"


def test_an_empty_chain_is_identity_in_a_node_call() -> None:
    story = _story({"a": [["node", "b"]], "b": []})
    assert run(story, "a", {"k": 1}) == {"k": 1}


def test_a_udf_may_answer_none() -> None:
    story = _story({"a": [["udf", "f"]]})
    assert run(story, "a", udfs={"f": lambda value: None}) is None


# ---------------------------------------------------------------- the README example (offline)


_README_STORY: dict[str, Any] = {
    "globals": {"base_url": "https://github.com"},
    "nodes": {
        "pinned": [
            ["node", "list"],
            ["each", [["udf", "claim"]]],
            ["py", "filter"],
            ["py", "first"],
            ["node", "detail"],
        ],
        "list": [
            ["py", "strip"],
            ["ctx", "dict", {"url": "obj"}],
            ["udf", "fetch"],
            ["py", "getattr", "text"],
            ["css", "nodes", "div.js-pinned-items-reorder-container ol > li"],
            ["each", {"url": [["css1", "@href", "a"], ["py", "urljoin", "$globals.base_url"]]}],
        ],
        "detail": [
            ["node", "detail_request"],
            ["udf", "fetch"],
            ["py", "sleep", 2],
            ["node", "detail_parse"],
        ],
        "detail_request": {"url": [["py", "getitem", "url"]]},
        "detail_parse": {
            "url": [["py", "getattr", "url"]],
            "status": [["py", "getattr", "status_code"]],
            "actions": [
                ["py", "getattr", "text"],
                ["css1", "text", '[class*="Actions"]'],
                ["py", "normalize_space"],
            ],
        },
    },
}


class _PinnedPage:
    # The same pinned URL twice: the README's `claim` must drop the second one before `first`.
    text = (
        '<div class="js-pinned-items-reorder-container"><ol>'
        '<li><a href="/ClericPy/awesome">one</a></li>'
        '<li><a href="/ClericPy/awesome">again</a></li>'
        "</ol></div>"
    )
    url = "https://github.com/ClericPy"
    status_code = 200


class _DetailPage:
    text = '<div class="Actions"><span>  Actions   </span></div>'
    url = "https://github.com/ClericPy/awesome"
    status_code = 200


def test_the_readme_example_runs_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """The README's GitHub template: list → claim/filter → first → detail → fetch → parse."""
    seen: set[str] = set()

    def fetch(request: Any) -> Any:
        key = request["url"]
        return _PinnedPage() if key == "https://github.com/ClericPy" else _DetailPage()

    def claim(item: Any) -> Any:
        """The toy external store: first sighting wins, a repeat answers ``None``."""
        if item["url"] in seen:
            return None
        seen.add(item["url"])
        return item

    monkeypatch.setattr("uniparser2.ops.pyops.time.sleep", lambda seconds: None)
    product = run(
        _README_STORY,
        "pinned",
        "https://github.com/ClericPy",
        udfs={"fetch": fetch, "claim": claim},
    )
    assert product == {
        "url": "https://github.com/ClericPy/awesome",
        "status": 200,
        "actions": "Actions",
    }


def test_a_claim_udf_and_filter_skip_seen_items() -> None:
    """The dedupe pattern: ``each claim`` maps a repeat to ``None``, ``py.filter`` drops it."""
    story = _story(
        {
            "items": [
                ["py", "const", [{"url": "a"}, {"url": "b"}, {"url": "a"}]],
                ["each", [["udf", "claim"]]],
                ["py", "filter"],
            ]
        }
    )
    seen: set[str] = set()

    def claim(item: Any) -> Any:
        if item["url"] in seen:
            return None
        seen.add(item["url"])
        return item

    assert run(story, "items", udfs={"claim": claim}) == [{"url": "a"}, {"url": "b"}]


def test_both_readmes_carry_the_tested_template() -> None:
    """The README block is the template the case above runs; a drift fails here."""
    root = Path(__file__).resolve().parents[2]
    for name in ("README.md", "README.zh-CN.md"):
        text = (root / name).read_text(encoding="utf-8")
        blocks = re.findall(r"```jsonc\n(.*?)```", text, re.S)
        story = next(
            json.loads(block) for block in blocks if '"nodes"' in block and '"pinned"' in block
        )
        assert story == _README_STORY
