"""``type`` operator: construct the declared type from the current value (design doc 03 §3).

The stage is ``["type", name]``: two slots, one action, the type name in slot 2. It is an ordinary
**constructor** stage and may appear anywhere in a chain: whatever the constructor answers is what
the chain carries on, so a container type carries a host object onward and a later stage reads it
with ``py.getattr`` or hands it to a ``udf`` (``03`` §3.3). JSON is required only at the run's exit,
where ``pack`` answers ``UP2-E2003`` for a non-JSON product.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar, Final

from ..core.ast import Lit, Param
from ..core.errors import Failed, Ok, Outcome
from ..core.registry import ActionSpec, Call, Kind, Op, ParamSpec, op
from ..core.types import (
    UNREGISTERED_FIX,
    TypeConstructionError,
    UnknownTypeError,
    build_type,
)

_TYPE_ACTION: Final = "check"


@op("type")
class TypeCheck(Op):
    """Build the registered type from the value and carry the constructed value on."""

    summary = "Construct the declared type from the value"
    arity = 2
    slot_roles = ("type",)
    actions: ClassVar[Mapping[str, ActionSpec]] = {
        _TYPE_ACTION: ActionSpec(
            _TYPE_ACTION,
            "Construct the declared type from the value",
            (ParamSpec("name", Kind.LITERAL),),
        )
    }

    def resolve_action(self, action_text: Any, *, pointer: str = "") -> str:
        del action_text, pointer  # single action: the stage omits the action slot
        return _TYPE_ACTION

    def precompile(self, action: str, params: Mapping[str, Param], *, pointer: str = "") -> Any:
        del action, pointer
        raw = params["name"]
        return raw.value if isinstance(raw, Lit) else raw

    def evaluate(self, call: Call) -> Outcome:
        name = call.payload
        if not isinstance(name, str):
            return Failed(
                code="UP2-E1011",
                reason=f"the type name must be a string, got {type(name).__name__}",
                fix=UNREGISTERED_FIX,
            )
        try:
            return Ok(build_type(name, call.value, table=call.scope.types or None))
        except UnknownTypeError as exc:
            return Failed(code="UP2-E1011", reason=str(exc), fix=UNREGISTERED_FIX)
        except TypeConstructionError as exc:
            return Failed(
                code="UP2-E2019",
                reason=f"the type {exc.name!r} rejected the value: {exc.reason}",
                fix="match the value's shape to the constructor, or fix the constructor",
            )
