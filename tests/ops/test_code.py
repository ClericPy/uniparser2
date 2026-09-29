"""``code`` operator (design doc 02 §6.12; the OpenSpec change ``add-code-sandbox-operator``).

Two layers:

1. **Stand-in / compile layer** (needs no ``pydantic-monty``): the parameter schema, reserved names,
   arity, the missing-dependency gate, handle rejection;
2. **Real sandbox layer** (``pytest.importorskip("pydantic_monty")``): the isolation boundary,
   limits, determinism, allowlisted functions, the tri-state mapping — these are
   **security-critical** and have to really run; a stand-in cannot paper over them.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

import uniparser2 as up2
from uniparser2.core import registry
from uniparser2.core.errors import Failed, Missing, Ok, Outcome
from uniparser2.core.refs import Scope
from uniparser2.ops import code as code_op
from uniparser2.ops.htmldom import DomNode

COVERS_PAIRS = (("code", "run"),)

# When the sandbox runtime (`uniparser2[code]`) is not installed, `code` is blocked at compile time
# by `UP2-E1107` and behaviour cases cannot exist at all — skipping the whole module is more honest
# than pretending a stand-in covers security-critical behaviour.
# The capability-gate and packaging-boundary cases live in `test_code_gate.py`; they need no
# sandbox at all.
_CODE_OP = registry.get("code")
assert _CODE_OP is not None  # importing uniparser2 registers it; this is a hard precondition
_MISSING = registry.op_missing_deps(_CODE_OP)
pytestmark = pytest.mark.skipif(bool(_MISSING), reason=f"sandbox runtime not installed: {_MISSING}")

_ROOT = Path(__file__).resolve().parents[2]


def _run(
    chain: Any,
    value: Any = None,
    *,
    locals_: dict[str, Any] | None = None,
    globals_: dict[str, Any] | None = None,
) -> Outcome:
    scope = Scope(locals=dict(locals_ or {}), globals=dict(globals_ or {}))
    return up2.eval_field(
        up2.compile_field(chain), value, scope=scope, policy=up2.Policy(on_missing="drop")
    )


def _code(src: str, **extra: Any) -> Any:
    return [["code", {"src": src, **extra}]]


def _failed(outcome: Outcome) -> Failed:
    assert isinstance(outcome, Failed), outcome
    return outcome


def _compile_error(chain: Any) -> tuple[str, str]:
    with pytest.raises(up2.Up2Error) as info:
        up2.compile_field(chain)
    return info.value.diagnostic.code, info.value.diagnostic.pointer


@pytest.fixture
def sandbox() -> Any:
    """Real sandbox: restore the default policy after every use (limits/clock are process state)."""
    module = pytest.importorskip("pydantic_monty")
    code_op.reset_policy()
    yield module
    code_op.reset_policy()


# ------------------------------------------------ 1. extra boundary and gate


# ------------------------------------------------ 2. parameter schema (compile time)


def test_missing_src_is_parameter_error() -> None:
    code, pointer = _compile_error([["code", {"inputs": {"x": 1}}]])
    assert code == "UP2-E1005"
    assert pointer == "/0/1"


def test_blank_src_is_rejected() -> None:
    with pytest.raises(up2.Up2Error) as info:
        up2.compile_field(_code("   "))
    assert info.value.diagnostic.code == "UP2-E1005"
    assert info.value.diagnostic.pointer == "/0/1/src"


def test_non_string_src_is_rejected() -> None:
    bad_src: Any = 123
    with pytest.raises(up2.Up2Error) as info:
        up2.compile_field(_code(bad_src))
    assert info.value.diagnostic.code == "UP2-E1005"


def test_third_slot_is_arity_error() -> None:
    code, pointer = _compile_error([["code", {"src": "1"}, "extra"]])
    assert code == "UP2-E1004"
    assert pointer == "/0"


def test_reserved_input_names_are_rejected() -> None:
    for reserved in ("obj", "ctx"):
        with pytest.raises(up2.Up2Error) as info:
            up2.compile_field(_code("1", inputs={reserved: 1}))
        assert info.value.diagnostic.code == "UP2-E1005"
        assert info.value.diagnostic.pointer == "/0/1/inputs"


def test_inputs_must_be_an_object() -> None:
    with pytest.raises(up2.Up2Error) as info:
        up2.compile_field(_code("1", inputs=["$locals.x"]))
    assert info.value.diagnostic.code == "UP2-E1005"


def test_dangling_reference_fails_at_compile_time() -> None:
    code, pointer = _compile_error(_code("x", inputs={"x": "$nope.n"}))
    assert code == "UP2-E1006"
    assert pointer == "/0/1"
    assert "$nope" not in str(pointer)


# ------------------------------------------------ 3. isolation and limits (real sandbox)


@pytest.mark.parametrize(
    ("src", "expected"),
    [
        ("open('C:/Windows/win.ini').read()", "PermissionError"),
        ("import os\nos.getenv('USERNAME')", "not supported"),
        ("import socket", "ModuleNotFoundError"),
        ("import subprocess", "ModuleNotFoundError"),
        ("__import__('os')", "NameError"),
        ("obj.__class__.__mro__[1].__subclasses__()", "AttributeError"),
    ],
)
def test_sandbox_cannot_reach_the_host(sandbox: Any, src: str, expected: str) -> None:
    """Inside the sandbox there is no filesystem/environment/network/process.

    There is no classic escape surface either — a failure must be observable.
    """
    outcome = _failed(_run(_code(src), "x"))
    assert outcome.code == "UP2-E2017"
    assert expected in outcome.reason


def test_unsupported_syntax_is_loud(sandbox: Any) -> None:
    outcome = _failed(_run(_code("class A:\n    pass\nclass B(A):\n    pass\n1")))
    assert outcome.code == "UP2-E2017"
    assert "NotImplementedError" in outcome.reason


def test_feed_duration_limit_trips(sandbox: Any) -> None:
    code_op.configure(max_feed_seconds=0.1)
    started = time.perf_counter()
    outcome = _failed(_run(_code("while True:\n    pass")))
    elapsed = time.perf_counter() - started
    assert outcome.code == "UP2-E2016"
    assert elapsed < code_op.current_policy().request_timeout


def test_memory_limit_trips_when_configured(sandbox: Any) -> None:
    code_op.configure(max_memory=8 * 1024 * 1024)
    outcome = _failed(_run(_code("len('a' * (100 * 1024 * 1024))")))
    assert outcome.code == "UP2-E2016"


def test_memory_limit_comes_from_host_config(sandbox: Any) -> None:
    """Counter-example: the limit is **not** a default the sandbox ships with.

    Raise the budget and the very same allocation goes through.
    """
    code_op.configure(max_memory=1 << 30)
    assert _run(_code("len('a' * (100 * 1024 * 1024))")) == Ok(100 * 1024 * 1024)


def test_round_trip_budget_must_be_positive(sandbox: Any) -> None:
    """A host round-trip budget of 0 makes the preloaded allowlisted functions uncallable outright.

    The default must therefore be positive (this case pins that down).
    """
    code_op.configure(max_round_trips=0)
    outcome = _failed(_run(_code("normalize_space(obj)"), "  a   b  "))
    assert outcome.code == "UP2-E2016"


def test_chain_cannot_widen_limits() -> None:
    code, _ = _compile_error(_code("1", max_memory=1 << 40))
    assert code == "UP2-E1005"


# ------------------------------------------------ 4. determinism and allowlisted functions


def test_repeated_runs_are_identical(sandbox: Any) -> None:
    src = (
        "from datetime import datetime\n"
        "import random, time\n"
        "f'{datetime.now():%Y-%m-%d %H:%M:%S} {random.random():.8f} {time.monotonic():.3f}'"
    )
    first = _run(_code(src))
    second = _run(_code(src))
    assert isinstance(first, Ok) and isinstance(second, Ok)
    assert first.value == second.value


def test_host_can_opt_out_of_frozen_clock(sandbox: Any) -> None:
    code_op.configure(frozen_clock=False)
    outcome = _run(_code("from datetime import datetime\ndatetime.now().year"))
    assert isinstance(outcome, Ok)
    assert outcome.value >= 2024  # follows the host clock instead of being frozen at 2000


def test_whitelist_functions_need_no_import(sandbox: Any) -> None:
    """What is mounted into the sandbox is the ``py`` function set, with the **same parameters**.

    The first positional argument is the value being processed, so ``urljoin``'s base still goes in
    the second argument (the same meaning as ``["py","urljoin",base]`` in a chain).
    """
    assert _run(_code("normalize_space(obj)"), "  a   b  ") == Ok("a b")
    assert _run(_code("urljoin(obj, 'https://x/')"), "a") == Ok("https://x/a")
    assert _run(_code("uniq(flatten([[1, 1], [2]]))")) == Ok([1, 2])


def test_whitelist_function_failure_is_catchable(sandbox: Any) -> None:
    """A preloaded function failing inside the sandbox is an exception.

    The snippet itself can catch it with try/except.
    """
    src = (
        "result = 'uncaught'\n"
        "try:\n"
        "    int('abc')\n"
        "except Exception:\n"
        "    result = 'caught'\n"
        "result"
    )
    assert _run(_code(src)) == Ok("caught")


def test_sandbox_stdlib_subset_is_available(sandbox: Any) -> None:
    outcome = _run(_code("import json, math, re\njson.dumps(re.findall(r'\\d+', obj))"), "a1b22")
    assert outcome == Ok('["1", "22"]')


# ------------------------------------------------ 5. obj / ctx / tri-state


def test_obj_is_the_upstream_value(sandbox: Any) -> None:
    assert _run(_code("len(obj)"), "abcd") == Ok(4)


def test_ctx_locals_and_globals_are_attribute_style(sandbox: Any) -> None:
    outcome = _run(
        _code("ctx.locals.n + 1"),
        None,
        locals_={"n": 41},
    )
    assert outcome == Ok(42)
    outcome = _run(
        _code("ctx.globals.base_url + str(len(obj))"),
        "abc",
        globals_={"base_url": "https://x/"},
    )
    assert outcome == Ok("https://x/3")


def test_ctx_locals_carries_values_written_by_the_chain(sandbox: Any) -> None:
    """A temporary variable an earlier stage wrote into locals is readable straight from code."""
    outcome = _run([["ctx", "set", "locals.k"], ["code", {"src": "ctx.locals.k"}]], "intermediate")
    assert outcome == Ok("intermediate")


def test_missing_ctx_attribute_is_loud(sandbox: Any) -> None:
    outcome = _failed(_run(_code("ctx.locals.nope")))
    assert outcome.code == "UP2-E2017"
    assert "AttributeError" in outcome.reason


def test_handles_are_excluded_from_ctx(sandbox: Any) -> None:
    """Handles do not appear in ctx, and that is **not an error**.

    It is the same principle as "a handle cannot leave the chain".
    """
    src = (
        "result = 'present'\n"
        "try:\n"
        "    ctx.locals.node\n"
        "except AttributeError:\n"
        "    result = 'absent'\n"
        "result"
    )
    outcome = _run(_code(src), None, locals_={"node": DomNode(object()), "text": "ok"})
    assert outcome == Ok("absent")


def test_ctx_assignment_does_not_flow_back(sandbox: Any) -> None:
    scope = Scope(locals={}, globals={})
    outcome = up2.eval_field(
        up2.compile_field(_code("ctx.locals.added = 7\n'ok'")), None, scope=scope
    )
    assert outcome == Ok("ok")
    assert "added" not in scope.locals


def test_named_inputs_are_available(sandbox: Any) -> None:
    outcome = _run(_code("x + 1", inputs={"x": "$locals.n"}), None, locals_={"n": 41})
    assert outcome == Ok(42)


def test_upstream_handle_is_rejected() -> None:
    outcome = _failed(_run(_code("1"), DomNode(object())))
    assert outcome.code == "UP2-E2003"


def test_non_json_return_is_rejected(sandbox: Any) -> None:
    outcome = _failed(_run(_code("{1, 2}")))
    assert outcome.code == "UP2-E2009"
    assert "set" in outcome.reason


def test_sandbox_exception_maps_to_e2017(sandbox: Any) -> None:
    outcome = _failed(_run(_code("1 / 0")))
    assert outcome.code == "UP2-E2017"
    assert "ZeroDivisionError" in outcome.reason


def test_return_value_is_last_expression(sandbox: Any) -> None:
    assert _run(_code("x = 1 + 1\nx * 3")) == Ok(6)
    assert _run(_code("x = 1 + 1")) == Ok(None)
    assert _run(_code("print('hi')")) == Ok(None)


def test_missing_policy_still_applies(sandbox: Any) -> None:
    """``code`` does not declare accepts_missing, so an upstream Missing short-circuits.

    The effective policy decides what comes out.
    """
    outcome = up2.eval_field(
        up2.compile_field([["ctx", "get", "locals.nope"], ["code", {"src": "1"}]]),
        None,
        policy=up2.Policy(on_missing="drop"),
    )
    assert isinstance(outcome, Missing)


# ------------------------------------------------ 6. policy API


def test_configure_rejects_unknown_keys(sandbox: Any) -> None:
    with pytest.raises(ValueError, match="unknown sandbox policy keys"):
        code_op.configure(max_mem=1)


def test_policy_changes_are_visible(sandbox: Any) -> None:
    policy = code_op.configure(max_memory=1234, frozen_clock=False)
    assert policy.max_memory == 1234
    assert code_op.current_policy().max_memory == 1234
    assert code_op.reset_policy().max_memory == code_op.DEFAULT_POLICY.max_memory
