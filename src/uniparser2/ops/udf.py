"""``udf`` operator: call a host-registered named function (design doc 02 §6.10).

The chain carries no source code; it names a function from **the run's table** (process-wide
`register_udf` defaults plus `run(udfs={...})`). A name the story uses but the table lacks is
`UP2-E1010`, reported by `run` before evaluation.

Four argument forms (the third slot selects the call):

================  ==========================================================
``["udf", f]``     ``f(value)`` — the upstream value as one DTO argument
``["udf", f, "*"]``  ``f(*value)`` — the upstream value must be a list
``["udf", f, "**"]`` ``f(**value)`` — the upstream value must be a mapping
``["udf", f, arg]``  ``f(arg)`` — one explicit argument
================  ==========================================================

A udf may answer **any** value: a response object flows to the next stage and is read with
``py.getattr``; only the run's exit and a ``["type", …]`` stage require JSON. An awaitable answer is
``UP2-E2009`` because the kernel is synchronous.
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from typing import Any, ClassVar, Final

from ..core.errors import Failed, Ok, Outcome, Up2Error, diag
from ..core.registry import ActionSpec, Call, Kind, Op, ParamSpec, op
from ..core.udfs import UNREGISTERED_FIX, get_udf, udf_names
from ..core.values import type_name

_NO_ARGUMENT: Final = object()
"""Slot 3 was omitted: the upstream value is the DTO argument."""

_DYNAMIC_SPEC: Final = ActionSpec(
    "call",
    "call a host-registered function (write the function name in slot 2)",
    (ParamSpec("argument", Kind.REF_OR_LITERAL, required=False, default=_NO_ARGUMENT),),
)


@op("udf")
class Udf(Op):
    """Host-registered function (the action slot is the function name)."""

    summary = "Host-registered named function (the chain carries no code)"
    dynamic_actions = True
    actions: ClassVar[Mapping[str, ActionSpec]] = {}

    def resolve_action(self, action_text: Any, *, pointer: str = "") -> str:
        if not isinstance(action_text, str) or not action_text or action_text.startswith("$"):
            raise Up2Error(
                diag(
                    "UP2-E1010",
                    f"slot 2 of udf must be a function name, got {action_text!r}",
                    fix=UNREGISTERED_FIX,
                    pointer=pointer,
                    allowed=udf_names(),
                )
            )
        return action_text

    def action_spec(self, action: str) -> ActionSpec:
        del action  # the dynamic action space shares a single schema
        return _DYNAMIC_SPEC

    def precompile(self, action: str, params: Mapping[str, Any], *, pointer: str = "") -> str:
        """Resolve the call form; check the registered signature when the function is known."""
        mode = _mode_of(params["argument"])
        function = get_udf(action)
        if function is not None and mode in ("dto", "arg"):
            takes_value = _check_signature(
                action, function, mode=mode, pointer=_action_pointer(pointer)
            )
            if mode == "dto" and not takes_value:
                return "nullary"
        return mode

    def dynamic_action_summary(self) -> str:
        names = udf_names()
        if not names:
            return f"no registered functions yet ({UNREGISTERED_FIX})"
        return "registered: " + ", ".join(names)

    def evaluate(self, call: Call) -> Outcome:
        function = call.scope.udfs.get(call.action) or get_udf(call.action)
        if function is None:
            return Failed(
                code="UP2-E1010",
                reason=f"the custom function {call.action!r} is not registered",
                fix=UNREGISTERED_FIX,
            )
        mode = call.payload
        if mode == "star":
            if not isinstance(call.value, (list, tuple)):
                return Failed(
                    code="UP2-E2002",
                    reason=f"udf.{call.action} with `*` needs a list, got {type_name(call.value)}",
                    fix="produce a list before the stage, or call the function with one DTO",
                )
            result = function(*call.value)
        elif mode == "dstar":
            if not isinstance(call.value, Mapping):
                return Failed(
                    code="UP2-E2002",
                    reason=(
                        f"udf.{call.action} with `**` needs a mapping, got {type_name(call.value)}"
                    ),
                    fix="produce an object before the stage, or call the function with one DTO",
                )
            if not all(isinstance(key, str) for key in call.value):
                return Failed(
                    code="UP2-E2002",
                    reason=f"udf.{call.action} with `**` needs string keys",
                    fix="build the mapping with string keys",
                )
            result = function(**call.value)
        elif mode == "arg":
            result = function(call.params["argument"])
        elif mode == "nullary" or _accepts_no_positional(function):
            result = function()
        else:
            result = function(call.value)
        if inspect.isawaitable(result):
            close = getattr(result, "close", None)
            if callable(close):
                close()
            return Failed(
                code="UP2-E2009",
                reason=f"udf.{call.action} answered an awaitable, and the kernel is synchronous",
                fix="call the async function in the host's own event loop and return its value",
            )
        return Ok(result)


def _mode_of(raw: Any) -> str:
    """The call form from the raw slot-3 parameter."""
    value = raw.value if hasattr(raw, "value") else raw
    if value is _NO_ARGUMENT:
        return "dto"
    if value == "*":
        return "star"
    if value == "**":
        return "dstar"
    return "arg"


def _action_pointer(pointer: str) -> str:
    """The function name is slot 2 of the stage; point the diagnostic there, not at slot 3."""
    return f"{pointer.rsplit('/', 1)[0]}/1" if "/" in pointer else "/0/1"


def _check_signature(function_name: str, function: Any, *, mode: str, pointer: str) -> bool:
    """Reject a signature the selected form cannot call; answer whether it takes the value."""
    try:
        parameters = list(inspect.signature(function).parameters.values())
    except (TypeError, ValueError):
        # A callable whose signature cannot be read is called with the value, the historical rule.
        return True
    positional = [
        parameter
        for parameter in parameters
        if parameter.kind
        in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    required = [parameter for parameter in positional if parameter.default is parameter.empty]
    required_keywords = [
        parameter
        for parameter in parameters
        if parameter.kind is inspect.Parameter.KEYWORD_ONLY and parameter.default is parameter.empty
    ]
    if required_keywords:
        names = ", ".join(parameter.name for parameter in required_keywords)
        raise Up2Error(
            diag(
                "UP2-E1005",
                f"the host function {function_name!r} requires the keyword-only arguments {names}",
                fix="bind them at registration, or pass them with the `**` form",
                pointer=pointer or "/0/1",
            )
        )
    if mode == "arg" and not positional and not _has_varargs(parameters):
        raise Up2Error(
            diag(
                "UP2-E1005",
                f"the host function {function_name!r} takes no positional argument, but the stage "
                "passes one",
                fix='write the stage as ["udf", name] to pass the upstream value, or register a '
                "function that accepts one argument",
                pointer=pointer or "/0/1",
            )
        )
    if len(required) > 1:
        names = ", ".join(parameter.name for parameter in required)
        raise Up2Error(
            diag(
                "UP2-E1005",
                f"the host function {function_name!r} requires the arguments {names}, and a udf "
                "stage passes at most one",
                fix="bind the extra arguments at registration (functools.partial), or use the `*` "
                "or `**` form",
                pointer=pointer or "/0/1",
            )
        )
    return bool(positional) or _has_varargs(parameters)


def _has_varargs(parameters: list[inspect.Parameter]) -> bool:
    return any(parameter.kind is inspect.Parameter.VAR_POSITIONAL for parameter in parameters)


def _accepts_no_positional(function: Any) -> bool:
    """Whether a dto call should be nullary: the function declares no positional parameter."""
    try:
        parameters = list(inspect.signature(function).parameters.values())
    except (TypeError, ValueError):
        return False
    return not any(
        parameter.kind
        in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.VAR_POSITIONAL,
        )
        for parameter in parameters
    )
