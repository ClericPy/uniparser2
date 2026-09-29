"""Runtime error codes checked one by one (design doc 02 §7.1)."""

from __future__ import annotations

from typing import Any

import pytest

from uniparser2 import (
    Failed,
    Ok,
    Opaque,
    Outcome,
    Policy,
    Scope,
    compile_field,
    eval_field,
    pack,
)
from uniparser2.core import registry
from uniparser2.ops import pyops


class FakeNode(Opaque):
    """A stand-in DOM handle: it may flow inside a chain, but the export must reject it."""


def run(
    chain: Any, value: Any, *, scope: Scope | None = None, policy: Policy | None = None
) -> Outcome:
    compiled = compile_field(chain)
    return eval_field(compiled, value, scope=scope, policy=policy or Policy(on_missing="drop"))


def test_e2001_traverse_into_scalar() -> None:
    scope = Scope(locals={"a": "text"})
    outcome = run([["ctx", "get", "locals.a.b"]], None, scope=scope)
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2001"


def test_e2001_unknown_product_at_runtime() -> None:
    compiled = compile_field([["py", "urljoin", "$n1.url"]], products=("n1",))
    outcome = eval_field(compiled, "x", policy=Policy(on_missing="drop"))
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


def test_e2015_missing_with_raise_policy() -> None:
    outcome = run([["re", "search", r"\d+"]], "abc", policy=Policy(on_missing="raise"))
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2015"


def _boom_evaluate(self: registry.Op, call: registry.Call) -> Outcome:
    raise RuntimeError("operator implementation exploded")


def test_e2099_unexpected_exception_becomes_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    from uniparser2.ops.pyops import Py

    monkeypatch.setattr(Py, "evaluate", _boom_evaluate)
    outcome = run([["py", "strip", ""]], " a ")
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2099"


def test_policy_on_error_drop_degrades_to_missing() -> None:
    from uniparser2 import Missing

    outcome = run([["re", "search", r"\d+"]], 12, policy=Policy(on_error="drop", on_missing="drop"))
    assert isinstance(outcome, Missing)


def test_policy_on_error_empty_degrades_to_empty_string() -> None:
    outcome = run([["re", "search", r"\d+"]], 12, policy=Policy(on_error="empty"))
    assert outcome == Ok("")


def test_policy_rejects_unknown_strategy() -> None:
    with pytest.raises(ValueError, match="on_missing"):
        Policy(on_missing="nope")
