"""``udf`` operator: host-registered functions (design doc 02 §6.10).

Coverage is declared as ``("udf", "*")``: that operator's action space is decided by the host, so
what conformance asks of it is **contract coverage** (an unregistered name reports `E1010`, a
registered one can be called, the return value must be serializable) rather than one case per
function name.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import pytest

from uniparser2 import (
    Failed,
    Ok,
    Outcome,
    Up2Error,
    compile_field,
    eval_field,
    host,
    register_udf,
)
from uniparser2.core.refs import Scope
from uniparser2.core.udfs import udf_names, unregister_udf

COVERS_PAIRS = (("udf", "*"),)


@pytest.fixture
def udfs() -> Iterator[Callable[[str, Callable[..., Any]], str]]:
    """Register temporary custom functions; they are removed when the test ends.

    The global registry is not polluted.
    """
    registered: list[str] = []

    def add(name: str, fn: Callable[..., Any]) -> str:
        register_udf(name, fn)
        registered.append(name)
        return name

    yield add
    for name in registered:
        unregister_udf(name)


def run(chain: Any, value: Any) -> Outcome:
    return eval_field(compile_field(chain), value)


def test_unregistered_function_fails_at_compile_time() -> None:
    """Unregistered means an error at compile time — it is not left to runtime."""
    with pytest.raises(Up2Error) as info:
        compile_field([["udf", "definitely_not_registered", ""]])
    assert info.value.diagnostic.code == "UP2-E1010"
    assert "register_udf" in info.value.diagnostic.fix


def test_action_slot_must_be_a_function_name() -> None:
    with pytest.raises(Up2Error) as info:
        compile_field([["udf", "$nope", ""]])
    assert info.value.diagnostic.code == "UP2-E1010"


def test_registered_function_is_called(udfs) -> None:
    udfs("up2_test_upper", lambda value: str(value).upper())
    assert run([["udf", "up2_test_upper", ""]], "abc") == Ok("ABC")


def test_kwargs_are_passed_through(udfs) -> None:
    def tagger(value: Any, prefix: str = "", suffix: str = "") -> str:
        return f"{prefix}{value}{suffix}"

    udfs("up2_test_tag", tagger)
    chain = [["udf", "up2_test_tag", {"prefix": "[", "suffix": "]"}]]
    assert run(chain, "x") == Ok("[x]")


# ------------------------------------------------ shared input convention with code (design D13)


def test_ctx_is_injected_when_the_signature_declares_it(udfs) -> None:
    """Declaring `ctx` injects the scope object: `ctx.locals.x` / `ctx.globals.y`.

    It is the same read style as in-chain code.
    """

    def reader(value: Any, ctx: Any) -> str:
        return f"{value}|{ctx.locals.tag}|{ctx.globals.base_url}"

    udfs("up2_test_ctx_reader", reader)
    scope = Scope(locals={"tag": "T"}, globals={"base_url": "https://x/"})
    outcome = eval_field(compile_field([["udf", "up2_test_ctx_reader", ""]]), "v", scope=scope)
    assert outcome == Ok("v|T|https://x/")


def test_signature_decides_injection(udfs) -> None:
    """The existing spellings that do not declare `ctx` (single argument / lambda) keep working."""
    udfs("up2_test_plain", lambda value: str(value).upper())
    assert run([["udf", "up2_test_plain", ""]], "abc") == Ok("ABC")


def test_ctx_is_a_reserved_parameter_name(udfs) -> None:
    """`ctx` is injected by the operator following the signature.

    Passing it as an ordinary parameter in the chain must therefore fail at compile time (it is
    never silently overridden).
    """
    udfs("up2_test_reserved", lambda value, ctx: value)
    with pytest.raises(Up2Error) as info:
        compile_field([["udf", "up2_test_reserved", {"ctx": 1}]])
    assert info.value.diagnostic.code == "UP2-E1005"
    assert info.value.diagnostic.pointer == "/0/2/kwargs"


def test_ctx_locals_writes_land_in_the_scope(udfs) -> None:
    """Host code receives the **live** scope: writing `ctx.locals` lands back in this evaluation."""

    def stasher(value: Any, ctx: Any) -> Any:
        ctx.locals.stashed = value
        return value

    udfs("up2_test_ctx_stasher", stasher)
    scope = Scope(locals={}, globals={})
    assert eval_field(compile_field([["udf", "up2_test_ctx_stasher", ""]]), "v", scope=scope) == Ok(
        "v"
    )
    assert scope.locals == {"stashed": "v"}


def test_ctx_globals_is_read_only(udfs) -> None:
    """`globals` being read-only is **structural**: writing it raises on the spot.

    It never fails silently (crossing the write boundary is a failure).
    """

    def hacker(value: Any, ctx: Any) -> Any:
        ctx.globals.hacked = 1
        return value

    udfs("up2_test_ctx_hacker", hacker)
    scope = Scope(locals={}, globals={"base_url": "https://x/"})
    outcome = eval_field(compile_field([["udf", "up2_test_ctx_hacker", ""]]), "v", scope=scope)
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2099"
    assert "TypeError" in outcome.reason
    assert scope.globals == {"base_url": "https://x/"}


def test_missing_ctx_attribute_is_loud(udfs) -> None:
    def reader(value: Any, ctx: Any) -> str:
        return str(ctx.locals.nope)

    udfs("up2_test_ctx_missing", reader)
    outcome = eval_field(
        compile_field([["udf", "up2_test_ctx_missing", ""]]), "v", scope=Scope(locals={})
    )
    assert isinstance(outcome, Failed)
    assert "AttributeError" in outcome.reason


def test_kwargs_names_are_host_defined(udfs) -> None:
    """``udf`` parameter names come from the host function and the compiler cannot check them.

    This is the key difference from the built-in operators.
    """
    seen: dict[str, Any] = {}

    def flexible(value: Any, **kwargs: Any) -> Any:
        seen.update(kwargs)
        return value

    udfs("up2_test_flexible", flexible)
    assert run([["udf", "up2_test_flexible", {"nope": 1}]], "x") == Ok("x")
    assert seen == {"nope": 1}


def test_host_function_rejecting_kwargs_surfaces_as_e2099(udfs) -> None:
    udfs("up2_test_strict", lambda value: value)
    outcome = run([["udf", "up2_test_strict", {"nope": 1}]], "x")
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2099"


def test_non_object_params_are_type_error(udfs) -> None:
    udfs("up2_test_noop", lambda value: value)
    outcome = run([["udf", "up2_test_noop", "not-a-dict"]], "x")
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2002"


def test_non_serialisable_return_is_e2009(udfs) -> None:
    udfs("up2_test_bad", lambda value: {1, 2})
    outcome = run([["udf", "up2_test_bad", ""]], "x")
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2009"
    assert "cannot be a product" in outcome.reason
    assert "list" in outcome.fix


def test_exception_inside_udf_becomes_e2099(udfs) -> None:
    def boom(value: Any) -> Any:
        raise RuntimeError("the host function blew up")

    udfs("up2_test_boom", boom)
    outcome = run([["udf", "up2_test_boom", ""]], "x")
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2099"


def test_function_can_make_use_of_upstream_value(udfs) -> None:
    udfs("up2_test_strip_prefix", lambda value: str(value).removeprefix("id:"))
    chain = [["py", "strip", ""], ["udf", "up2_test_strip_prefix", ""]]
    assert run(chain, "  id:42  ") == Ok("42")


def test_dynamic_action_summary_lists_registered_names(udfs) -> None:
    from uniparser2.core import registry

    udfs("up2_test_alpha", lambda value: value)
    report = {item.name: item for item in registry.report()}["udf"]
    assert report.actions[0].name == "*"
    assert "up2_test_alpha" in report.actions[0].summary


def test_registered_names_are_sorted(udfs) -> None:
    udfs("up2_test_b", lambda value: value)
    udfs("up2_test_a", lambda value: value)
    assert udf_names() == ("up2_test_a", "up2_test_b")


def test_entry_point_loading_skips_broken_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Entry:
        name = "up2_test_broken"

        def load(self) -> Any:
            raise ImportError("broken entry")

    monkeypatch.setattr(host, "entry_points", lambda group: [_Entry()])
    assert host.load_entry_point_udfs() == ()


def test_entry_point_loading_registers_good_entries(monkeypatch: pytest.MonkeyPatch, udfs) -> None:
    class _Entry:
        name = "up2_test_from_ep"

        def load(self) -> Any:
            return lambda value: f"ep:{value}"

    monkeypatch.setattr(host, "entry_points", lambda group: [_Entry()])
    assert host.load_entry_point_udfs() == ("up2_test_from_ep",)
    assert run([["udf", "up2_test_from_ep", ""]], "x") == Ok("ep:x")
    unregister_udf("up2_test_from_ep")
