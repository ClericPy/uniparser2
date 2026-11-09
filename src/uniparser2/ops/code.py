"""``code`` operator: sandboxed execution of in-chain code (design doc 02 §6.12).

**Slots** (see ``02`` §1): ``["code", {"src": …, "inputs": {…}}]`` — **only 2 slots**: it has
exactly one action (run this source once), so the chain omits the action slot (the same shape as
``json`` / ``const``).

**Two fixed parameter names** (the same convention as ``udf``, design D3/D13):

- ``obj``: the upstream value;
- ``ctx``: a **scope object**, used attribute-style as ``ctx.locals.args1`` / ``ctx.globals.base``.
  ``ctx`` is built inside the sandbox from the JSON projection of the scope by a **prelude** (code
  inside the sandbox), hence zero host round-trips; non-JSON values such as ``Opaque`` handles in
  ``locals`` never appear (they could not leave the chain anyway, ``UP2-E2003``).
- The return value = **the value of the last expression** (REPL semantics); if the source ends with
  an assignment / ``print`` / a comment, it is ``None``.

**Isolation**: the sandbox has no file, environment, network or process operations; this operator
**mounts no host capability at all** and only passes JSON values in. The only thing mounted is the
**engine's own pure functions** (the same source as the ``py`` allowlist), so snippets do not have
to ``import``; each call counts as one host round-trip and is bounded by ``max_round_trips``.

**Limits live on the host side only** (design D7): chain data cannot override them; the default is
deterministic (frozen clock + fixed timezone + sleep disabled + seeded random), see
:class:`SandboxPolicy`. **The limits are not on by default** — without an explicit memory budget a
500 MB allocation succeeds, so they are pinned item by item here.

**Assignments to ``ctx`` inside the sandbox do not flow back** into the engine scope (design D3:
Monty does not dispatch ``__setattr__``, and ``dir`` / ``vars`` / ``__dict__`` do not exist, so
dynamically added keys cannot be enumerated back); use ``ctx.set`` on the chain to write the scope.
"""

from __future__ import annotations

import atexit
import contextlib
import importlib
import os
import sysconfig
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, Final

from ..core.ast import Lit, Param
from ..core.errors import Failed, Ok, Outcome, Up2Error, diag
from ..core.refs import Scope
from ..core.registry import ActionSpec, Call, Kind, Op, ParamSpec, op
from ..core.values import Opaque, is_json_value, type_name
from . import pyops

_MONTY: Final = "pydantic_monty"
_EXTRA: Final = 'uv add "uniparser2[code]"'
_RUN: Final = "run"
_FROZEN_INSTANT: Final = datetime(2000, 1, 1)
_UNLIMITED_HINT: Final = (
    "limits are configured by the host (uniparser2.ops.code.configure); "
    "the chain cannot change them"
)
_LIMIT_KINDS: Final = ("TimeoutError", "MemoryError")

_PRELUDE: Final = '''
class _Ns:
    """Recursively turn a dict into an attribute-style namespace for ctx.locals.args1."""

    def __init__(self, data):
        for key in data:
            value = data[key]
            setattr(self, key, _Ns(value) if isinstance(value, dict) else value)


ctx = _Ns(data)
'''
"""The prelude snippet: build the ``ctx`` object inside the sandbox (zero host round-trips)."""


@dataclass(frozen=True, slots=True)
class SandboxPolicy:
    """The **host-side** policy of the sandbox: limits + determinism + the worker binary path.

    Chain data can never override it.
    """

    max_memory: int = 64 * 1024 * 1024
    max_feed_seconds: float = 0.5
    request_timeout: float = 5.0
    max_round_trips: int = 1000
    frozen_clock: bool = True
    seeded_random: bool = True
    binary_path: str | None = None


DEFAULT_POLICY: Final = SandboxPolicy()
_POLICY: SandboxPolicy = DEFAULT_POLICY
_POOL: Any = None
_POOL_POLICY: SandboxPolicy | None = None
_LOOKUP: dict[str, Callable[..., Any]] | None = None


def current_policy() -> SandboxPolicy:
    """The sandbox policy currently in effect (used by ``up2 ops`` and the tests)."""
    return _POLICY


def configure(**changes: Any) -> SandboxPolicy:
    """Override the sandbox policy on the host side and return the policy in effect.

    Changes are applied item by item on top of the current values. Changing the policy discards the
    already-built sandbox pool (it is rebuilt on the next evaluation); unknown keys raise
    immediately, so "configured but not in effect" cannot happen.
    """
    global _POLICY
    unknown = sorted(set(changes) - set(SandboxPolicy.__dataclass_fields__))
    if unknown:
        raise ValueError(
            f"unknown sandbox policy keys: {unknown} "
            f"(available: {sorted(SandboxPolicy.__dataclass_fields__)})"
        )
    _POLICY = replace(_POLICY, **changes)
    _close_pool()
    return _POLICY


def reset_policy() -> SandboxPolicy:
    """Restore the default policy and drop the cached mount table (mainly for the tests)."""
    global _POLICY, _LOOKUP
    _POLICY = DEFAULT_POLICY
    _LOOKUP = None
    _close_pool()
    return _POLICY


def _limits() -> dict[str, Any]:
    """Pin the limits explicitly on every checkout.

    The sandbox defaults must not be relied on: there is no memory budget and no timeout by
    default.
    """
    return {
        "max_memory": _POLICY.max_memory,
        "max_feed_duration_secs": _POLICY.max_feed_seconds,
        "max_suspensions": _POLICY.max_round_trips,
    }


def _os_policy() -> dict[str, Any]:
    """Deterministic defaults: frozen clock + fixed timezone + sleep disabled + seeded random.

    The host may explicitly turn the first two off.
    """
    policy: dict[str, Any] = {"sleep": "zero"}
    if _POLICY.frozen_clock:
        policy["datetime"] = _FROZEN_INSTANT
        policy["timezone"] = "utc"
    if _POLICY.seeded_random:
        policy["random_start"] = {"seed": 0}
    return policy


def _close_pool() -> None:
    global _POOL, _POOL_POLICY
    if _POOL is not None:
        with contextlib.suppress(Exception):  # closing the pool must not affect the caller
            _POOL.__exit__(None, None, None)
    _POOL = None
    _POOL_POLICY = None


def _worker_binary() -> str | None:
    """The worker binary path: an explicit host setting wins, otherwise pin the packaged one.

    Otherwise the copy packaged with the runtime **inside the environment** is pinned. When it is
    not found, return ``None`` and let the upstream resolve it in its own order (``binary_path`` →
    ``MONTY_BIN`` → the packaged runtime → ``PATH`` → the cargo development build). **We do not
    search ``PATH`` ourselves** — this is also this module's only say over "which binary the
    sandbox uses".
    """
    if _POLICY.binary_path is not None:
        return _POLICY.binary_path
    scripts = sysconfig.get_path("scripts")
    if not scripts:
        return None
    candidate = Path(scripts) / ("monty.exe" if os.name == "nt" else "monty")
    return str(candidate) if candidate.exists() else None


def _sandbox() -> Any:
    """Hold the sandbox pool lazily (the same shape as ``htmldom._ENGINE``).

    The pool must be in context-manager state before a checkout can happen.
    """
    global _POOL, _POOL_POLICY
    if _POOL is not None and _POOL_POLICY == _POLICY:
        return _POOL
    _close_pool()
    module = importlib.import_module(_MONTY)
    kwargs: dict[str, Any] = {"request_timeout": _POLICY.request_timeout}
    binary = _worker_binary()
    if binary is not None:
        kwargs["binary_path"] = binary
    pool = module.Monty(**kwargs)
    pool.__enter__()
    _POOL = pool
    _POOL_POLICY = _POLICY
    return pool


atexit.register(_close_pool)


def _mount(name: str) -> Callable[..., Any]:
    """Mount one ``py`` allowlist function into the sandbox (positional arguments → parameters)."""

    def mounted(*args: Any) -> Any:
        outcome = pyops.call_positional(name, args, _EMPTY_SCOPE)
        if isinstance(outcome, Ok):
            return outcome.value
        reason = getattr(outcome, "reason", "missing")
        raise RuntimeError(f"{name}: {reason}")

    return mounted


def sandbox_functions() -> Mapping[str, Callable[..., Any]]:
    """The engine pure functions mounted into the sandbox.

    Actions with missing dependencies are skipped.
    """
    global _LOOKUP
    if _LOOKUP is None:
        from ..core import registry

        instance = registry.get("py")
        lookup: dict[str, Callable[..., Any]] = {}
        for name in pyops.functions():
            if instance is not None and registry.action_missing_deps(instance, name):
                continue
            lookup[name] = _mount(name)
        _LOOKUP = lookup
    return _LOOKUP


_EMPTY_SCOPE: Final = Scope()
"""The allowlist functions mounted for the sandbox are pure (they do not read the scope), so an
empty scope suffices.
"""


def _literal_text(params: Mapping[str, Param], name: str, *, pointer: str = "") -> str:
    value = params.get(name)
    if value is None:
        raise Up2Error(
            diag(
                "UP2-E1005",
                f"missing required parameter {name!r}",
                fix="add src",
                pointer=pointer,
            )
        )
    text = value.value if isinstance(value, Lit) else value
    if not isinstance(text, str):
        raise Up2Error(
            diag(
                "UP2-E1005",
                f"parameter {name!r} must be a string, got {type_name(text)}",
                fix='write src as a source string, e.g. "len(obj)"',
                pointer=pointer,
            )
        )
    if not text.strip():
        raise Up2Error(
            diag(
                "UP2-E1005",
                "src cannot be a blank string",
                fix='write some source, e.g. "len(obj)" or "ctx.locals.n + 1"',
                pointer=pointer,
            )
        )
    return text


def _sandbox_failure(exc: Exception) -> Failed:
    """Translate a sandbox exception into our tri-state error codes.

    Limits / code exceptions / crashes are kept apart.
    """
    name = type(exc).__name__
    text = str(exc).splitlines()[0] if str(exc) else name
    if name == "MontyCrashedError":
        return Failed(
            code="UP2-E2099",
            reason=f"the sandbox worker crashed: {text}",
            fix="run it again; if it reproduces reliably, report it with the chain and the inputs",
        )
    if name == "MontyConversionError":
        return Failed(
            code="UP2-E2009",
            reason=f"sandbox value conversion failed: {text}",
            fix=(
                "restrict inputs and return values to the JSON value domain "
                "(str/int/float/bool/None/list/dict)"
            ),
        )
    if name in ("MontyDisconnectError", "MontyShutdown"):
        return Failed(
            code="UP2-E2099",
            reason=f"sandbox unavailable: {text}",
            fix="rebuild the sandbox: restart the process, or retry after configure()",
        )
    if name == "MontySyntaxError":
        return Failed(
            code="UP2-E2017",
            reason=f"sandbox syntax error: {text}",
            fix="fix src; the sandbox implements only a subset of Python 3.14 (see Monty docs)",
        )
    if name == "MontyTypingError":  # type checking is off; seeing this is unexpected
        return Failed(
            code="UP2-E2017",
            reason=f"sandbox type check failed: {text}",
            fix="fix src as the type-check message suggests",
        )
    return _runtime_failure(text)


def _runtime_failure(text: str) -> Failed:
    """``MontyRuntimeError``: classify by the type of the inner exception.

    Limits / unsupported syntax / code exceptions are kept apart.
    """
    kind = text.split(":", 1)[0].strip()
    if kind in _LIMIT_KINDS or "limit" in text:
        return Failed(
            code="UP2-E2016",
            reason=f"sandbox execution exceeded its limits: {text}",
            fix=f"reduce the data volume or rewrite the algorithm; {_UNLIMITED_HINT}",
        )
    if kind == "NotImplementedError":
        return Failed(
            code="UP2-E2017",
            reason=f"the sandbox does not support this syntax: {text}",
            fix=(
                "see Monty's limitations documentation (class inheritance, generators, match and "
                "del are unsupported)"
            ),
        )
    return Failed(
        code="UP2-E2017",
        reason=f"the sandboxed code raised an exception: {text}",
        fix="fix src; the snippet can catch it itself with try/except",
    )


@op("code")
class Code(Op):
    """In-chain code (sandboxed; optional dependency ``[code]``, absent by default)."""

    summary = "In-chain code (sandboxed; optional dependency [code])"
    requires = (_MONTY,)
    arity = 2
    slot_roles = ("source",)
    actions: ClassVar[Mapping[str, ActionSpec]] = {
        _RUN: ActionSpec(
            _RUN,
            "run src once and take the value of the last expression",
            (ParamSpec("src", Kind.LITERAL),),
        )
    }

    def resolve_action(self, action_text: Any, *, pointer: str = "") -> str:
        del action_text, pointer  # single action: the chain omits the action slot
        return _RUN

    def precompile(self, action: str, params: Mapping[str, Param], *, pointer: str = "") -> Any:
        del action
        if not _code_enabled():
            raise Up2Error(
                diag(
                    "UP2-E1107",
                    "the code operator is disabled by UP2_CODE=off",
                    fix="set UP2_CODE=on (or unset it) to run in-chain code, or use a udf",
                    pointer=pointer,
                )
            )
        _literal_text(params, "src", pointer=f"{pointer}/src")
        return None

    def evaluate(self, call: Call) -> Outcome:
        if not _code_enabled():  # pragma: no cover - compile time already refused it
            return Failed(
                code="UP2-E1107",
                reason="the code operator is disabled by UP2_CODE=off",
                fix="set UP2_CODE=on (or unset it), or use a udf",
            )
        src = call.params["src"]
        if not isinstance(src, str):  # pragma: no cover - guaranteed at compile time
            return Failed(code="UP2-E2002", reason=f"src must be a string, got {type_name(src)}")
        problem = _bad_value("obj", call.value)
        if problem is not None:
            return problem
        try:
            module = importlib.import_module(_MONTY)
        except ImportError as exc:
            return Failed(
                code="UP2-E1107",
                reason=f"code needs pydantic-monty: {exc}",
                fix=f"install the optional dependency: {_EXTRA}",
            )
        try:
            pool = _sandbox()
        except Exception as exc:  # a pool that fails to start also becomes a coded Failed
            return Failed(
                code="UP2-E2099",
                reason=f"the sandbox pool failed to start: {exc}",
                fix=f"make sure the optional dependency is installed: {_EXTRA}",
            )
        return _run_in_sandbox(module, pool, src, call.value, call.scope.json_view())


def _code_enabled() -> bool:
    """``UP2_CODE=off`` disables the operator before any sandbox work (design D9)."""
    return os.environ.get("UP2_CODE", "on").strip().lower() not in ("off", "0", "false", "no")


def _silence_print(stream: str, text: str) -> None:
    """In-chain ``print`` output is dropped: the product is the channel, not stdout (D9)."""
    del stream, text


def _bad_value(name: str, value: Any) -> Failed | None:
    """The sandbox accepts JSON values only: handles and non-JSON values are rejected here.

    They are not silently dropped.
    """
    if isinstance(value, Opaque):
        return Failed(
            code="UP2-E2003",
            reason=f"{name} is a node handle and cannot enter the sandbox",
            fix="convert the handle to text with text / @<attribute> first, then pass it to code",
        )
    if not is_json_value(value):
        return Failed(
            code="UP2-E2009",
            reason=f"{name} is not a JSON value: {type_name(value)}",
            fix="restrict inputs to str/int/float/bool/None/list/dict",
        )
    return None


def _run_in_sandbox(
    module: Any,
    pool: Any,
    src: str,
    obj: Any,
    data: Mapping[str, Any],
) -> Outcome:
    """Run the snippet after the ``ctx`` prelude and translate the outcome to the tri-state."""
    try:
        with pool.checkout(limits=_limits(), os_policy=_os_policy()) as session:
            session.feed_run(_PRELUDE, inputs={"data": data})
            result = session.feed_run(
                src,
                inputs={"obj": obj},
                external_lookup=sandbox_functions(),
                print_callback=_silence_print,
            )
    except module.MontyError as exc:
        return _sandbox_failure(exc)
    if not is_json_value(result):
        return Failed(
            code="UP2-E2009",
            reason=f"code returned a value that cannot be a product: {type_name(result)}",
            fix="restrict the return value to str/int/float/bool/None/list/dict",
        )
    return Ok(result)
