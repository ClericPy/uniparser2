"""Runtime error codes checked one by one (design doc 02 §7.1)."""

from __future__ import annotations

from typing import Any

import pytest

from uniparser2 import (
    Failed,
    Ok,
    Opaque,
    Outcome,
    Scope,
    compile_field,
    eval_field,
    pack,
)
from uniparser2.core import registry
from uniparser2.ops import pyops


class FakeNode(Opaque):
    """A stand-in DOM handle: it may flow inside a chain, but the export must reject it."""


class _HostResponse:
    """A stand-in host object (what an HTTP client would hand over): read with py.getattr."""

    __slots__ = ("status", "text")

    def __init__(self, status: int, text: str) -> None:
        self.status = status
        self.text = text

    def headers(self) -> dict[str, str]:
        """A method: a dotted reference must refuse it, exactly as `py.getattr` does."""
        return {}

    def json(self) -> dict[str, Any]:
        """The `requests`-style method an author reaches for by mistake."""
        return {}


_CALLABLE_FIX = (
    'a method is not a value: read the text with ["css","text",""] (or "html" / '
    '"outer"), or register a udf that calls it'
)
"""The fix hint both refusals carry (`refs._walk_attribute`, `pyops._py_getattr`)."""


def run(chain: Any, value: Any, *, scope: Scope | None = None) -> Outcome:
    compiled = compile_field(chain)
    return eval_field(compiled, value, scope=scope)


def test_e2001_reference_walks_a_host_object() -> None:
    """A dotted path dispatches per value kind: a mapping by key, an object by getattr."""
    scope = Scope(locals={"resp": _HostResponse(200, "body")})
    assert run([["ctx", "get", "locals.resp.text"]], None, scope=scope) == Ok("body")


def test_e2001_reference_missing_attribute_names_the_class() -> None:
    scope = Scope(locals={"resp": _HostResponse(200, "body")})
    outcome = run([["ctx", "get", "locals.resp.txet"]], None, scope=scope)
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2001"
    assert "AttributeError: '_HostResponse' object has no attribute 'txet'" in outcome.reason


def test_e2002_reference_refuses_a_callable_attribute() -> None:
    """A dotted reference never calls a method, exactly as `py.getattr` never does (03 §13 O12)."""
    scope = Scope(locals={"resp": _HostResponse(200, "body")})
    outcome = run([["ctx", "get", "locals.resp.headers"]], None, scope=scope)
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2002"
    assert "the attribute 'headers' of _HostResponse is callable" in outcome.reason
    assert outcome.fix == _CALLABLE_FIX


def test_the_reference_and_getattr_refusals_agree() -> None:
    """The same message shape and the same fix hint, so an author sees one rule, not two."""
    response = _HostResponse(200, "body")
    reference = run([["ctx", "get", "locals.r.json"]], None, scope=Scope(locals={"r": response}))
    attribute = run([["py", "getattr", "json"]], response)
    assert isinstance(reference, Failed) and isinstance(attribute, Failed)
    assert reference.code == attribute.code == "UP2-E2002"
    assert reference.fix == attribute.fix


def test_e2001_reference_indexes_a_sequence() -> None:
    scope = Scope(locals={"rows": ["a", "b"]})
    assert run([["ctx", "get", "locals.rows.1"]], None, scope=scope) == Ok("b")


@pytest.mark.parametrize(
    ("path", "needle"),
    [
        ("locals.rows.first", "tried to index a list"),
        ("locals.rows.9", "out of range"),
    ],
)
def test_e2001_bad_sequence_index(path: str, needle: str) -> None:
    scope = Scope(locals={"rows": ["a", "b"]})
    outcome = run([["ctx", "get", path]], None, scope=scope)
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2001"
    assert needle in outcome.reason


def test_e2001_traverse_into_scalar() -> None:
    scope = Scope(locals={"a": "text"})
    outcome = run([["ctx", "get", "locals.a.b"]], None, scope=scope)
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2001"


def test_e2001_unknown_product_at_runtime() -> None:
    compiled = compile_field([["py", "urljoin", "$n1.url"]], products=("n1",))
    outcome = eval_field(compiled, "x")
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2001"
    assert "n1" in outcome.reason


def test_e2002_re_on_non_text() -> None:
    outcome = run([["re", "search", r"\d+"]], 12)
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2002"


def test_e2002_text_function_on_non_text() -> None:
    outcome = run([["py", "upper", ""]], [1, 2])
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2002"


def test_e2003_pack_rejects_opaque() -> None:
    outcome = pack(FakeNode())
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2003"
    # The fix names the accessor actions (``core/export.py``: text / html / outer / @attribute).
    assert "text" in outcome.fix


def test_e2003_pack_rejects_non_json() -> None:
    outcome = pack({"a": {1, 2}})
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2003"


def test_e2003_pack_rejects_a_host_object() -> None:
    """A host object may flow, but it can never be a product (design doc 03 §3.3)."""
    outcome = pack(_HostResponse(200, "body"))
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2003"
    assert "_HostResponse" in outcome.reason


def test_e2003_pack_rejects_a_host_object_nested_in_a_product() -> None:
    outcome = pack({"answer": _HostResponse(200, "body")})
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2003"


def test_a_host_object_flows_through_a_stage_unchanged() -> None:
    """The value that flows may be an object: a stage reads it, nothing converts it."""
    response = _HostResponse(200, "body")
    assert run([["py", "getattr", "status"]], response) == Ok(200)
    # A whole-chain reference hands the same object on unchanged (`03` §2).
    assert eval_field(compile_field("$in"), response, scope=Scope(step_input=response)) == Ok(
        response
    )


def test_e2003_pack_accepts_json() -> None:
    assert pack({"a": [1, None, True]}) == Ok({"a": [1, None, True]})


def _boom_import() -> Any:
    raise ImportError("no html_to_markdown in this environment")


def _no_missing_deps(instance: registry.Op, action: str) -> tuple[str, ...]:
    del instance, action
    return ()


def test_e2004_lazy_import_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """find_spec passes but the real import fails (broken install): this must report E2004."""
    monkeypatch.setattr(registry, "action_missing_deps", _no_missing_deps)
    monkeypatch.setattr(pyops, "_import_html_to_markdown", _boom_import)
    outcome = run([["py", "html_to_markdown", ""]], "<b>a</b>")
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2004"
    assert "html_to_markdown" in outcome.reason
    assert "uniparser2[md]" in outcome.fix


class _FakeConversion:
    """A stand-in result: the real ``convert()`` returns an object carrying ``.content``."""

    def __init__(self, content: Any) -> None:
        self.content = content


def test_real_html_to_markdown_converts(monkeypatch: pytest.MonkeyPatch) -> None:
    """With the real library installed, ``convert(...).content`` is the Markdown text."""
    pytest.importorskip("html_to_markdown")
    outcome = run([["py", "html_to_markdown", ""]], "<h1>T</h1><p>a <b>b</b></p>")
    assert isinstance(outcome, Ok)
    assert "# T" in outcome.value and "**b**" in outcome.value


def test_non_text_conversion_result_is_e2005(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pyops, "_import_html_to_markdown", lambda: lambda html: _FakeConversion(7))
    outcome = run([["py", "html_to_markdown", ""]], "<b>a</b>")
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2005"
    assert "non-text" in outcome.reason


def test_e2005_split_with_empty_separator() -> None:
    outcome = run([["py", "split", ""]], "ab")
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2005"


def _boom_evaluate(self: registry.Op, call: registry.Call) -> Outcome:
    raise RuntimeError("operator implementation exploded")


def test_e2099_unexpected_exception_becomes_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    from uniparser2.ops.pyops import Py

    monkeypatch.setattr(Py, "evaluate", _boom_evaluate)
    outcome = run([["py", "strip", ""]], " a ")
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2099"
