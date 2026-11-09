"""``udf`` operator: call a host-registered named function (design doc 02 §6.10, design D10).

The fundamental difference from the old v3 ``udf``: **the chain carries no source code**. The chain
can only name a function, while the body is reviewed and registered by the host beforehand; an
unregistered name fails at compile time with ``UP2-E1010``.

The action slot is the function name, so this operator's action space is **dynamic**
(``dynamic_actions = True``, the static ``actions`` empty): ``up2 conformance`` declares its
contract coverage with ``*``.

**A call is unary or nullary** (D10). The upstream value is the only positional argument
(``f(value)``), or there is none when the function declares no positional parameter (``f()``). The
stage writes no parameter slot, so the chain cannot configure the call; a function that needs
configuration takes a payload the chain builds with ``ctx``:

    ["ctx","dict",{"value":"obj","lang":"globals.lang"}]
    ["udf","translate"]

The registered signature is known at compile time, so a function that requires a second argument —
or a required keyword-only argument — is ``UP2-E1005`` before the run starts. ``ctx`` is no longer
injected: a parameter named ``ctx`` is an ordinary parameter of the host function.
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from typing import Any, ClassVar, Final

from ..core.errors import Failed, Ok, Outcome, Up2Error, diag
from ..core.registry import ActionSpec, Call, Op, op
from ..core.udfs import UNREGISTERED_FIX, get_udf, udf_names
from ..core.values import is_json_value, type_name

_DYNAMIC_SPEC: Final = ActionSpec(
    "call", "call a host-registered function (write the function name in slot 2)"
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
                    f"slot 2 of udf must be a registered function name, got {action_text!r}",
                    fix=UNREGISTERED_FIX,
                    pointer=pointer,
                    allowed=udf_names(),
                )
            )
        if get_udf(action_text) is None:
            raise Up2Error(
                diag(
                    "UP2-E1010",
                    f"the custom function {action_text!r} is not registered",
                    fix=UNREGISTERED_FIX,
                    pointer=pointer,
                    allowed=udf_names(),
                )
            )
        return action_text

    def action_spec(self, action: str) -> ActionSpec:
        del action  # the dynamic action space shares a single schema
        return _DYNAMIC_SPEC

    def precompile(self, action: str, params: Mapping[str, Any], *, pointer: str = "") -> bool:
        """Check the registered signature; answer whether the value is passed to it."""
        del params
        function = get_udf(action)
        if function is None:  # pragma: no cover - resolve_action already rejected it
            raise Up2Error(
                diag(
                    "UP2-E1010",
                    f"the custom function {action!r} is not registered",
                    fix=UNREGISTERED_FIX,
                    pointer=pointer,
                )
            )
        return _check_signature(action, function, pointer=_action_pointer(pointer))

    def dynamic_action_summary(self) -> str:
        names = udf_names()
        if not names:
            return f"no registered functions yet ({UNREGISTERED_FIX})"
        return "registered: " + ", ".join(names)

    def evaluate(self, call: Call) -> Outcome:
        function = get_udf(call.action)
        if function is None:  # pragma: no cover - registration is guaranteed at compile time
            return Failed(
                code="UP2-E1010",
                reason=f"the custom function {call.action!r} is not registered",
                fix=UNREGISTERED_FIX,
            )
        result = function(call.value) if call.payload else function()
        if not is_json_value(result):
            return Failed(
                code="UP2-E2009",
                reason=f"udf.{call.action} returned a value that cannot be a product: "
                f"{type_name(result)}",
                fix="restrict the return value to str/int/float/bool/None/list/dict",
            )
        return Ok(result)


def _action_pointer(pointer: str) -> str:
    """The function name is slot 2 of the stage; point the diagnostic there, not at slot 3."""
    return f"{pointer.rsplit('/', 1)[0]}/1" if "/" in pointer else "/0/1"


def _check_signature(function_name: str, function: Any, *, pointer: str) -> bool:
    """Reject a signature the stage cannot call; answer whether it takes the upstream value."""
    try:
        parameters = list(inspect.signature(function).parameters.values())
    except (TypeError, ValueError):
        # A callable whose signature cannot be read is called as unary, the historical behaviour.
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
    if len(required) > 1 or required_keywords:
        names = ", ".join(parameter.name for parameter in (*required, *required_keywords))
        raise Up2Error(
            diag(
                "UP2-E1005",
                f"the host function {function_name!r} requires the arguments {names}, and a udf "
                "stage passes only the upstream value",
                fix="bind the extra arguments at registration (functools.partial), or take one "
                "payload object built with ctx",
                pointer=pointer or "/0/1",
            )
        )
    takes_value = bool(positional) or any(
        parameter.kind is inspect.Parameter.VAR_POSITIONAL for parameter in parameters
    )
    return takes_value
