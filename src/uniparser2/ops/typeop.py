"""``type`` operator: validate a chain's product against the host type registry (design doc 03 §3).

The stage is ``["type", name]``: two slots, one action, the type name in slot 2. It is a
**chain-tail** stage: the compiler rejects a later stage (``UP2-E1005``). The constructor is a
validator, not a container: the stage answers the JSON the constructor approved, so the run carries
JSON and the single exit (`pack`) stays comparable.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import is_dataclass
from typing import Any, ClassVar, Final

from ..core.ast import Lit, Param
from ..core.errors import Failed, Ok, Outcome
from ..core.export import pack
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
    """Build the registered type from the value and carry the validated JSON on."""

    summary = "Validate the value against a registered type"
    arity = 2
    slot_roles = ("type",)
    actions: ClassVar[Mapping[str, ActionSpec]] = {
        _TYPE_ACTION: ActionSpec(
            _TYPE_ACTION,
            "Validate the value against a registered type",
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
            built = build_type(name, call.value)
        except UnknownTypeError:
            return Failed(
                code="UP2-E1011",
                reason=f"the type {name!r} is not registered",
                fix=UNREGISTERED_FIX,
            )
        except TypeConstructionError as exc:
            return Failed(
                code="UP2-E2019",
                reason=f"the type {exc.name!r} rejected the value: {exc.reason}",
                fix="match the value's shape to the constructor, or fix the constructor",
            )
        carried = pack(built)
        product = built if not isinstance(carried, Failed) else _same_json(built, call.value)
        packed = pack(product)
        if isinstance(packed, Failed):
            return packed
        return Ok(product)


def _same_json(built: Any, product: Any) -> Any:
    """The JSON a validating dataclass approved: the payload it was handed (`03` §3.3).

    A dataclass (or a model) answers an object, which cannot be a product; what it **approved** is
    the payload, so that is what the run carries on -- whatever its shape (an object, a list, a
    scalar). Returning the payload is also what keeps a field the payload does not carry out of the
    product: the payload's own shape decides what continues. A non-dataclass answer that is not JSON
    (a set, an arbitrary object) still fails ``pack`` with ``UP2-E2003``.
    """
    if is_dataclass(built) and not isinstance(built, type):
        return product
    return built
