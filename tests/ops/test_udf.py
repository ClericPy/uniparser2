"""``udf`` operator: host-registered functions (design doc 02 §6.10).

Coverage is declared as ``("udf", "*")``: that operator's action space is decided by the host, so
what conformance asks of it is **contract coverage** (a name missing from the run's table reports
`E1010`, a registered one can be called in each argument form) rather than one case per function
name. A udf may answer a host object mid-chain; the run's exit is what requires JSON.
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
from uniparser2 import (
    run as run_story,
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


def test_unregistered_function_fails_before_evaluation() -> None:
    """The table is run state, so a missing name is reported by `run` before the run starts."""
    compile_field([["udf", "definitely_not_registered"]])  # syntax only: no table at compile time
    with pytest.raises(Up2Error) as info:
        run_story({"nodes": {"a": [["udf", "definitely_not_registered"]]}}, "a")
    assert info.value.diagnostic.code == "UP2-E1010"
    assert "register_udf" in info.value.diagnostic.fix


def test_action_slot_must_be_a_function_name() -> None:
    with pytest.raises(Up2Error) as info:
        compile_field([["udf", "$nope"]])
    assert info.value.diagnostic.code == "UP2-E1010"


def test_registered_function_is_called(udfs) -> None:
    udfs("up2_test_upper", lambda value: str(value).upper())
    assert run([["udf", "up2_test_upper"]], "abc") == Ok("ABC")


# ------------------------------------------------ unary / nullary and the payload pattern (D10)


def test_signature_decides_injection(udfs) -> None:
    """The existing spellings that do not declare `ctx` (single argument / lambda) keep working."""
    udfs("up2_test_plain", lambda value: str(value).upper())
    assert run([["udf", "up2_test_plain"]], "abc") == Ok("ABC")


def test_nullary_function_is_called_without_the_value(udfs) -> None:
    udfs("up2_test_clock", lambda: "fixed")
    assert run([["udf", "up2_test_clock"]], "ignored") == Ok("fixed")


def test_an_optional_second_argument_is_allowed(udfs) -> None:
    def tagger(value: Any, prefix: str = "[") -> str:
        return f"{prefix}{value}]"

    udfs("up2_test_tagger", tagger)
    assert run([["udf", "up2_test_tagger"]], "x") == Ok("[x]")


def test_a_required_second_argument_is_a_compile_error(udfs) -> None:
    def two(value: Any, other: Any) -> str:
        return f"{value}{other}"

    udfs("up2_test_two", two)
    with pytest.raises(Up2Error) as info:
        compile_field([["udf", "up2_test_two"]])
    assert info.value.diagnostic.code == "UP2-E1005"
    assert info.value.diagnostic.pointer == "/0/1"
    assert "functools.partial" in info.value.diagnostic.fix


def test_a_payload_replaces_the_older_kwargs(udfs) -> None:
    def translate(payload: Any) -> str:
        return f"{payload['value']}-{payload['lang']}"

    udfs("up2_test_translate", translate)
    chain = [
        ["ctx", "dict", {"value": "obj", "lang": "globals.lang"}],
        ["udf", "up2_test_translate"],
    ]
    scope = Scope(globals={"lang": "fr"})
    assert eval_field(compile_field(chain), "hi", scope=scope) == Ok("hi-fr")


def test_a_host_object_return_flows_mid_chain(udfs) -> None:
    """A udf may answer any value, and the exit hands it back unchecked."""
    udfs("up2_test_bad", lambda value: {1, 2})
    assert run([["udf", "up2_test_bad"]], "x") == Ok({1, 2})
    assert run_story({"nodes": {"a": [["udf", "up2_test_bad"]]}}, "a") == {1, 2}


def test_exception_inside_udf_becomes_e2099(udfs) -> None:
    def boom(value: Any) -> Any:
        raise RuntimeError("the host function blew up")

    udfs("up2_test_boom", boom)
    outcome = run([["udf", "up2_test_boom"]], "x")
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2099"


def test_function_can_make_use_of_upstream_value(udfs) -> None:
    udfs("up2_test_strip_prefix", lambda value: str(value).removeprefix("id:"))
    chain = [["py", "strip"], ["udf", "up2_test_strip_prefix"]]
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
    assert run([["udf", "up2_test_from_ep"]], "x") == Ok("ep:x")
    unregister_udf("up2_test_from_ep")
