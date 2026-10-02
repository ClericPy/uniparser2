"""``css`` / ``css1`` operators (design doc 02 §6.1).

The slots are ``["css", accessor, selector]`` (the accessor first, the selector second).

Coverage has two layers:

1. **Stand-in engine** (runs by default): verifies the operator's own logic — the two operators
   differ only in cardinality (``css`` yields a list, ``css1`` a scalar), an empty selector takes
   the current node, ``remove`` returns a copy and ``css1`` prunes the first match only, nodes are
   wrapped in ``Opaque`` (the export must reject them), an invalid selector ⇒ compile-time
   ``E1005``, a missing engine ⇒ ``E1107``.
2. **Real engine** (runs only when installed): the same set of semantic assertions under
   ``selectolax`` (``text`` excludes the noise tags, inner/outer HTML, ``remove`` is a copy).
"""

from __future__ import annotations

from typing import Any

import pytest

from uniparser2 import (
    Failed,
    Missing,
    Ok,
    Opaque,
    Outcome,
    Up2Error,
    compile_field,
    eval_field,
    pack,
)
from uniparser2.core import registry
from uniparser2.ops import htmldom

COVERS_PAIRS = (
    ("css", "text"),
    ("css", "html"),
    ("css", "outer"),
    ("css", "self"),
    ("css", "nodes"),
    ("css", "remove"),
    ("css", "@<attribute>"),
    ("css1", "text"),
    ("css1", "html"),
    ("css1", "outer"),
    ("css1", "self"),
    ("css1", "nodes"),
    ("css1", "remove"),
    ("css1", "@<attribute>"),
)

_DOC = {"text": "DOC", "html": "<doc/>", "outer": "<doc/>", "attrs": {}}
_TITLE = {
    "text": "Title",
    "html": "<h1>Title</h1>",
    "outer": "<h1>Title</h1>",
    "attrs": {"id": "t"},
}
_LINK1 = {"text": "One", "html": "<a>One</a>", "outer": "<a>One</a>", "attrs": {"href": "/p/1"}}
_LINK2 = {"text": "Two", "html": "<a>Two</a>", "outer": "<a>Two</a>", "attrs": {}}
_BY_SELECTOR = {"h1": [_TITLE], "a": [_LINK1, _LINK2], "none": []}

# accessor → (all matches for css, the first for css1)
_EXPECTED: dict[str, tuple[list[str], str]] = {
    "text": (["One", "Two"], "One"),
    "html": (["<a>One</a>", "<a>Two</a>"], "<a>One</a>"),
    "outer": (["<a>One</a>", "<a>Two</a>"], "<a>One</a>"),
}


class FakeEngine:
    """Scripted stand-in: ``select`` / ``select_first`` return preset nodes by selector name."""

    name = "fake"

    def __init__(self) -> None:
        self.pruned: list[tuple[str, bool]] = []

    def parse(self, text: str) -> Any:
        return {**_DOC, "text": text, "html": text, "outer": text, "source": text}

    def select(self, node: Any, selector: str) -> list[Any]:
        return list(_BY_SELECTOR.get(selector, []))

    def select_first(self, node: Any, selector: str) -> Any | None:
        matched = self.select(node, selector)
        return matched[0] if matched else None

    def text(self, node: Any) -> str:
        return str(node["text"])

    def inner_html(self, node: Any) -> str:
        return str(node["html"])

    def outer_html(self, node: Any) -> str:
        return str(node["outer"])

    def attr(self, node: Any, name: str) -> str | None:
        value = node.get("attrs", {}).get(name)
        return None if value is None else str(value)

    def prune(self, node: Any, selector: str, *, first_only: bool = False) -> Any:
        self.pruned.append((selector, first_only))
        return {**node, "pruned": selector, "first_only": first_only}

    def validate(self, selector: str) -> None:
        if selector == "!!!":
            raise ValueError("invalid selector")


def _no_missing_deps(instance: object, action: str) -> tuple[str, ...]:
    del instance, action
    return ()


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeEngine:
    """Replace the engine and bypass the "engine availability" gate.

    The stand-in needs no real selectolax.
    """
    instance = FakeEngine()
    monkeypatch.setattr(htmldom, "engine", lambda: instance)
    monkeypatch.setattr(registry, "action_missing_deps", _no_missing_deps)
    return instance


def run(chain: Any, value: Any) -> Outcome:
    return eval_field(compile_field(chain), value)


@pytest.mark.parametrize("action", ["text", "html", "outer"])
def test_css_collects_all_matches(fake: FakeEngine, action: str) -> None:
    expected, _ = _EXPECTED[action]
    assert run([["css", action, "a"]], "<p>x</p>") == Ok(expected)


@pytest.mark.parametrize("action", ["text", "html", "outer"])
def test_css1_takes_first_match(fake: FakeEngine, action: str) -> None:
    _, expected = _EXPECTED[action]
    assert run([["css1", action, "a"]], "<p>x</p>") == Ok(expected)


def test_attr_action_returns_list_and_first_scalar(fake: FakeEngine) -> None:
    assert run([["css", "@href", "a"]], "<p>x</p>") == Ok(["/p/1"])
    assert run([["css1", "@href", "a"]], "<p>x</p>") == Ok("/p/1")


def test_attr_missing_is_missing_for_both(fake: FakeEngine) -> None:
    assert isinstance(run([["css", "@href", "h1"]], "<p>x</p>"), Missing)
    assert isinstance(run([["css1", "@href", "h1"]], "<p>x</p>"), Missing)


def test_attr_without_name_is_action_error() -> None:
    with pytest.raises(Up2Error) as info:
        compile_field([["css", "@", "a"]])
    assert info.value.diagnostic.code == "UP2-E1002"


def test_unknown_action_is_e1002() -> None:
    with pytest.raises(Up2Error) as info:
        compile_field([["css", "innerHTML", "a"]])
    assert info.value.diagnostic.code == "UP2-E1002"


def test_nodes_returns_opaque_list(fake: FakeEngine) -> None:
    outcome = run([["css", "nodes", "a"]], "<p>x</p>")
    assert isinstance(outcome, Ok)
    assert len(outcome.value) == 2
    assert all(isinstance(node, Opaque) for node in outcome.value)


def test_css1_nodes_returns_at_most_one(fake: FakeEngine) -> None:
    outcome = run([["css1", "nodes", "a"]], "<p>x</p>")
    assert isinstance(outcome, Ok)
    assert len(outcome.value) == 1


def test_self_returns_first_match_as_opaque(fake: FakeEngine) -> None:
    outcome = run([["css", "self", "h1"]], "<p>x</p>")
    assert isinstance(outcome, Ok)
    assert isinstance(outcome.value, Opaque)


def test_empty_selector_uses_context_itself(fake: FakeEngine) -> None:
    assert run([["css", "text", ""]], "hello") == Ok(["hello"])
    assert run([["css1", "text", ""]], "hello") == Ok("hello")


def test_no_match_is_missing(fake: FakeEngine) -> None:
    assert isinstance(run([["css", "text", "none"]], "<p>x</p>"), Missing)
    assert isinstance(run([["css1", "text", "none"]], "<p>x</p>"), Missing)
    assert isinstance(run([["css", "nodes", "none"]], "<p>x</p>"), Missing)


def test_node_handles_cannot_escape_through_pack(fake: FakeEngine) -> None:
    """The output of ``nodes`` / ``self`` must be rejected by export boxing.

    That is what wrapping in ``Opaque`` is for.
    """
    outcome = run([["css", "nodes", "a"]], "<p>x</p>")
    assert isinstance(outcome, Ok)
    packed = pack(outcome.value)
    assert isinstance(packed, Failed)
    assert packed.code == "UP2-E2003"


def test_remove_prunes_all_for_css_and_first_for_css1(fake: FakeEngine) -> None:
    all_matches = run([["css", "remove", "h1"]], "<p>x</p>")
    first_only = run([["css1", "remove", "h1"]], "<p>x</p>")
    assert isinstance(all_matches, Ok) and isinstance(first_only, Ok)
    assert all_matches.value.raw["first_only"] is False
    assert first_only.value.raw["first_only"] is True
    assert fake.pruned == [("h1", False), ("h1", True)]


def test_remove_with_empty_selector_is_noop(fake: FakeEngine) -> None:
    outcome = run([["css", "remove", ""]], "<p>x</p>")
    assert isinstance(outcome, Ok)
    assert fake.pruned == []


def test_invalid_selector_is_schema_error(fake: FakeEngine) -> None:
    with pytest.raises(Up2Error) as info:
        compile_field([["css", "text", "!!!"]])
    assert info.value.diagnostic.code == "UP2-E1005"


def test_engine_absent_reports_e1107(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(htmldom, "engine", lambda: None)
    monkeypatch.setattr(registry, "action_missing_deps", _no_missing_deps)
    outcome = run([["css", "text", "h1"]], "<p>x</p>")
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E1107"


def test_engine_absent_makes_op_unavailable_at_compile_time() -> None:
    """With selectolax missing, compile time must report E1107 plus the install command.

    It must not wait until runtime.
    """
    css = registry.get("css")
    assert css is not None
    if not registry.op_missing_deps(css):
        pytest.skip("selectolax is installed on this machine")
    with pytest.raises(Up2Error) as info:
        compile_field([["css", "text", "h1"]])
    assert info.value.diagnostic.code == "UP2-E1107"
    assert any("uniparser2[html]" in hint for hint in info.value.diagnostic.allowed)


def test_list_input_is_type_failure(fake: FakeEngine) -> None:
    outcome = run([["css", "text", "h1"]], [1, 2])
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2002"


def test_non_text_non_node_input_is_type_failure(fake: FakeEngine) -> None:
    outcome = run([["css", "text", "h1"]], 42)
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2002"


def test_chain_hands_node_to_next_step(fake: FakeEngine) -> None:
    """The node produced by the previous stage can be fed straight to the next one (``DomNode``)."""
    assert run([["css", "self", "h1"], ["css1", "text", ""]], "<p>x</p>") == Ok("Title")
    assert run([["css", "self", "h1"], ["css", "text", ""]], "<p>x</p>") == Ok(["Title"])


def test_real_engine_contract() -> None:
    """Semantic assertions on the real selectolax.

    They cover ``text`` excluding the noise tags, inner/outer HTML, and pruning being a copy.
    """
    pytest.importorskip("selectolax")
    active = htmldom.SelectolaxEngine()
    html = (
        "<html><body>"
        '<h1 id="t">Title</h1>'
        '<a href="/p/1">One</a><a href="/p/2">Two</a>'
        "<script>bad()</script><style>.x{}</style><noscript>N</noscript>"
        '<div class="c">D<b>B</b>E</div>'
        "</body></html>"
    )
    doc = active.parse(html)
    links = active.select(doc, "a")
    assert len(links) == 2
    assert active.attr(active.select_first(doc, "a"), "href") == "/p/1"
    assert active.text(active.select(doc, "h1")[0]).strip() == "Title"
    box = active.select(doc, "div.c")[0]
    assert active.inner_html(box) == "D<b>B</b>E"
    assert active.outer_html(box).startswith("<div")
    # Noise-tag semantics: the text of script/style/noscript must be excluded.
    assert active.text(doc).replace(" ", "").endswith("TitleOneTwoDBE")
    # Pruning happens "on a copy": the original document is untouched.
    pruned = active.prune(doc, "script")
    assert "bad()" not in active.outer_html(pruned)
    assert "bad()" in active.outer_html(doc)
    assert len(active.select(pruned, "a")) == 2
    active.validate("a[href]")


def test_empty_selector_compiles_on_real_engine() -> None:
    """Regression: the real engine **does reject an empty selector**.

    The empty string is still the legal spelling of "take the current node itself". The stand-in
    engine's ``validate`` does not reject it, so only the real engine exposes this — compile time
    must short-circuit the empty string before ``validate``.
    """
    pytest.importorskip("selectolax")
    compile_field([["css1", "text", ""]])
    compile_field([["css", "nodes", ""]])
    compile_field([["css1", "remove", ""]])
