"""``udf`` operator: call a host-registered named function (design doc 02 §6.10).

The fundamental difference from the old v3 ``udf`` (essence §5-R10): **the chain carries no source
code**. The chain can only supply a function name plus parameters, while the function body is
reviewed and registered by the host beforehand; an unregistered name fails at compile time with
``UP2-E1010``. Rule data therefore cannot introduce new code, and there is no ``eval``/``exec``
escape surface.

The action slot is the function name, so this operator's action space is **dynamic**
(``dynamic_actions = True``, the static ``actions`` empty): ``up2 conformance`` declares its
contract coverage with ``*`` (an unregistered name errors + a registered one is callable) rather
than function name by function name.

**The parameter convention matches ``code``** (design D13): the first positional parameter is the
upstream value; named parameters go in the object in slot 3; when the function **declares a ``ctx``
parameter** a scope object is injected according to the signature (``ctx.locals.x`` /
``ctx.globals.y``, the same accessors as ``ctx`` in in-chain code). Nothing is injected when it is
not declared, so existing single-parameter functions are unchanged. ``ctx`` is a reserved parameter
name — passing it as an ordinary parameter in the chain fails at compile time (``UP2-E1005``).
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping, MutableMapping
from types import MappingProxyType
from typing import Any, ClassVar, Final

from ..core.ast import Lit
from ..core.errors import Failed, Ok, Outcome, Up2Error, diag
from ..core.refs import CTX_PARTITIONS, Scope
from ..core.registry import ActionSpec, Call, Kind, Op, ParamSpec, op
from ..core.udfs import UNREGISTERED_FIX, get_udf, udf_names
from ..core.values import is_json_value, type_name

_DYNAMIC_SPEC: Final = ActionSpec(
    "call",
    "call a host-registered function (write the function name in slot 2)",
    (ParamSpec("kwargs", Kind.REF_OR_LITERAL, required=False, default=None),),
)

_RESERVED: Final = ("ctx",)
"""Reserved parameter name: injected by the operator by signature.

The chain cannot pass it as an ordinary parameter.
"""


class Namespace:
    """Attribute-style view: ``ctx.locals.args1`` ⇄ ``"args1"`` in the underlying mapping.

    Reading a missing key raises ``AttributeError`` (it does not silently return an empty value);
    writing succeeds only when the underlying mapping is writable, otherwise ``TypeError``
    (``globals`` is read-only, consistent with the kernel invariants).
    """

    __slots__ = ("_data",)

    def __init__(self, data: Mapping[str, Any]) -> None:
        object.__setattr__(self, "_data", data)

    def __getattr__(self, name: str) -> Any:
        data = object.__getattribute__(self, "_data")
        if name not in data:
            raise AttributeError(f"{name!r} does not exist")
        value = data[name]
        return Namespace(value) if isinstance(value, Mapping) else value

    def __setattr__(self, name: str, value: Any) -> None:
        data = object.__getattribute__(self, "_data")
        if not isinstance(data, MutableMapping):
            raise TypeError(
                f"{type(data).__name__} is read-only (globals read-only, locals writable)"
            )
        data[name] = value

    def __delattr__(self, name: str) -> None:
        data = object.__getattribute__(self, "_data")
        if not isinstance(data, MutableMapping):
            raise TypeError(
                f"{type(data).__name__} is read-only (globals read-only, locals writable)"
            )
        if name not in data:
            raise AttributeError(f"{name!r} does not exist")
        del data[name]

    def as_dict(self) -> dict[str, Any]:
        """Flatten into a plain dict.

        Only JSON values are kept; handles and non-JSON values are dropped.
        """
        data = object.__getattribute__(self, "_data")
        return {
            key: value
            for key, value in data.items()
            if isinstance(key, str) and is_json_value(value)
        }


class CtxView:
    """The ``ctx`` passed to host functions: ``ctx.locals.x`` / ``ctx.globals.y``.

    Same name and same accessors as ``ctx`` in in-chain code; the difference is that this is a
    **live scope** — ``udf`` runs on the host side, so writes to ``ctx.locals`` land directly in the
    scope of the current evaluation, while ``ctx.globals`` is read-only.
    """

    __slots__ = ("_scope",)

    def __init__(self, scope: Scope) -> None:
        object.__setattr__(self, "_scope", scope)

    def __getattr__(self, name: str) -> Namespace:
        scope = object.__getattribute__(self, "_scope")
        if name == "locals":
            return Namespace(scope.locals)
        if name == "globals":
            # Read-only is **structural**: it proxies an immutable mapping, so a write raises
            # TypeError on the spot (it is not a documentation convention).
            return Namespace(MappingProxyType(dict(scope.globals)))
        raise AttributeError(f"ctx has no {name!r} (available: {', '.join(CTX_PARTITIONS)})")


def _wants_ctx(function: Any) -> bool:
    """Whether the function declares a ``ctx`` parameter.

    Injection follows the signature; callables whose signature cannot be inspected get nothing.
    """
    try:
        parameters = inspect.signature(function).parameters
    except (TypeError, ValueError):
        return False
    if "ctx" not in parameters:
        return False
    return parameters["ctx"].kind in (
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.KEYWORD_ONLY,
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

    def precompile(self, action: str, params: Mapping[str, Any], *, pointer: str = "") -> Any:
        del action
        reserved = sorted(name for name in _kwargs_names(params) if name in _RESERVED)
        if reserved:
            raise Up2Error(
                diag(
                    "UP2-E1005",
                    f"reserved names cannot be used as parameters: {reserved}",
                    fix="ctx is injected by function signature; pick another parameter name",
                    pointer=f"{pointer}/kwargs",
                    allowed=tuple(f"not {name}" for name in _RESERVED),
                )
            )
        return None

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
        kwargs = call.params.get("kwargs")
        if kwargs is None:
            kwargs = {}
        if not isinstance(kwargs, dict):
            return Failed(
                code="UP2-E2002",
                reason=f"udf.{call.action} parameters must be an object, got {type_name(kwargs)}",
                fix='write a named-parameter object such as {"strict": true}',
            )
        if _wants_ctx(function):
            kwargs = {**kwargs, "ctx": CtxView(call.scope)}
        result = function(call.value, **kwargs)
        if not is_json_value(result):
            return Failed(
                code="UP2-E2009",
                reason=f"udf.{call.action} returned a non-serializable value: {type_name(result)}",
                fix="restrict the return value to str/int/float/bool/None/list/dict",
            )
        return Ok(result)


def _kwargs_names(params: Mapping[str, Any]) -> tuple[str, ...]:
    """The key names in the parameter object in slot 3 (used for the reserved-name check)."""
    raw = params.get("kwargs")
    value = raw.value if isinstance(raw, Lit) else raw
    if not isinstance(value, Mapping):
        return ()
    return tuple(str(key) for key in value)
