"""``json`` operator: jmespath queries (design doc 02 §6.2).

jmespath is an optional dependency, so there are two layers of coverage:
1. **Stand-in** (runs by default): verifies this operator's glue logic — whether the input is JSON
   text or an already-parsed value, no match ⇒ ``Missing``, an invalid expression ⇒ compile-time
   ``E1005``, a query-time exception ⇒ ``E2005``;
2. **Real jmespath** (runs only when installed): verifies the wiring against the real library.
"""

from __future__ import annotations

from typing import Any

import pytest

from uniparser2 import Failed, Missing, Ok, Outcome, Up2Error, compile_field, eval_field
from uniparser2.core import registry
from uniparser2.ops import jsonquery

COVERS_PAIRS = (("json", "get"),)


class _FakeCompiled:
    """A minimal stand-in: just enough (empty expression / dotted path / `[*]` projection)."""

    def __init__(self, expr: str) -> None:
        self.expr = expr

    def search(self, data: Any) -> Any:
        expr = self.expr
        if expr == "":
            return data
        if expr == "boom":
            raise RuntimeError("the query blew up")
        if "[*]." in expr:
            head, _, tail = expr.partition("[*].")
            items = data.get(head, []) if isinstance(data, dict) else []
            return [item.get(tail) for item in items if isinstance(item, dict)]
        current = data
        for segment in expr.split("."):
            if not isinstance(current, dict) or segment not in current:
                return None
            current = current[segment]
        return current


class _FakeJmespath:
    @staticmethod
    def compile(expr: str) -> _FakeCompiled:
        if expr == "(":
            raise ValueError("invalid expression")
        return _FakeCompiled(expr)


@pytest.fixture
def fake_jmespath(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace jmespath: bypass both the dependency gate and the real query implementation."""
    monkeypatch.setattr(jsonquery, "_import_jmespath", lambda: _FakeJmespath)
    monkeypatch.setattr(registry, "action_missing_deps", lambda instance, action: ())


def run(chain: Any, value: Any) -> Outcome:
    return eval_field(compile_field(chain), value)


def test_action_is_unavailable_without_jmespath() -> None:
    """This skips itself when jmespath is installed; when it is absent, unavailability is reported
    instead of a silent wrong value.
    """
    missing = registry.missing_deps(("jmespath",))
    if not missing:
        pytest.skip("jmespath is installed; this machine takes the real path")
    op = registry.get("json")
    assert op is not None
    with pytest.raises(Up2Error) as info:
        compile_field([["json", "data.html"]])
    assert info.value.diagnostic.code == "UP2-E1107"
    assert any("uniparser2[json]" in hint for hint in info.value.diagnostic.allowed)


def test_query_json_text(fake_jmespath: None) -> None:
    assert run([["json", "data.html"]], '{"data": {"html": "<p>x</p>"}}') == Ok("<p>x</p>")


def test_query_already_parsed_value(fake_jmespath: None) -> None:
    assert run([["json", "a"]], {"a": 1}) == Ok(1)


def test_empty_expression_returns_root(fake_jmespath: None) -> None:
    assert run([["json", ""]], {"a": 1}) == Ok({"a": 1})


def test_projection_returns_list(fake_jmespath: None) -> None:
    data = {"items": [{"url": "u1"}, {"url": "u2"}]}
    assert run([["json", "items[*].url"]], data) == Ok(["u1", "u2"])


def test_no_match_is_missing(fake_jmespath: None) -> None:
    assert isinstance(run([["json", "nope"]], {"a": 1}), Missing)


def test_invalid_expression_is_schema_error(fake_jmespath: None) -> None:
    with pytest.raises(Up2Error) as info:
        compile_field([["json", "("]])
    assert info.value.diagnostic.code == "UP2-E1005"
    assert "jmespath" in info.value.diagnostic.message


def test_bad_json_text_is_e2005(fake_jmespath: None) -> None:
    outcome = run([["json", "a"]], "{oops")
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2005"


def test_non_json_input_is_type_failure(fake_jmespath: None) -> None:
    """``12`` is a legal JSON value, so a plain no-match is only ``Missing``.

    A non-JSON value (a set, say) is the one that reports ``UP2-E2002``.
    """
    assert isinstance(run([["json", "a"]], 12), Missing)
    outcome = run([["json", "a"]], {"a": {1, 2}})
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2002"


def test_query_exception_is_e2005(fake_jmespath: None) -> None:
    outcome = run([["json", "boom"]], {"a": 1})
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2005"


def test_alias_jmespath_works(fake_jmespath: None) -> None:
    assert run([["jmespath", "a"]], {"a": 2}) == Ok(2)


def test_legacy_action_slot_is_arity_error(fake_jmespath: None) -> None:
    """``json`` has a single behaviour (``action_slot = None``), so the stage writes no action slot.

    The old 3-slot shape ``["json", "$get", "a"]`` now has one slot too many ⇒ ``UP2-E1004`` (the
    arity has to be exact).
    """
    with pytest.raises(Up2Error) as info:
        compile_field([["json", "get", "a"]])
    assert info.value.diagnostic.code == "UP2-E1004"


def test_real_jmespath_when_installed() -> None:
    pytest.importorskip("jmespath")
    text = '{"data": {"list": [{"url": "u1"}, {"url": "u2"}]}}'
    assert run([["json", "data.list[*].url"]], text) == Ok(["u1", "u2"])
    assert isinstance(run([["json", "data.nope"]], text), Missing)
