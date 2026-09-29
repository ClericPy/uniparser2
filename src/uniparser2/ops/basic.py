"""Building-block operator: ``const`` (design doc 02 §6.5).

Two-slot operator ``[const, value]``: it has **exactly one action**, so the chain omits the action
slot and slot 2 is the literal produced verbatim.

Type conversion (the former ``cast`` operator) has been folded back into ``py``: ``str`` / ``int`` /
``float`` / ``bool`` / ``list`` / ``from_json`` — these are Python built-ins to begin with, and a
standalone operator would only add another "where does the target type go" convention (see D-02-14
in ``02``).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar, Final

from ..core.errors import Ok, Outcome
from ..core.registry import ActionSpec, Call, Kind, Op, ParamSpec, op

_CONST_ACTION: Final = "const"


@op("const")
class Const(Op):
    """Produce the literal verbatim.

    ``["const", "$100"]`` yields the string ``"$100"`` (never resolved as a reference).
    """

    summary = "Literal (never resolved as a reference)"
    arity = 2
    slot_roles = ("value",)
    actions: ClassVar[Mapping[str, ActionSpec]] = {
        _CONST_ACTION: ActionSpec(
            _CONST_ACTION,
            "Produce the value verbatim",
            (ParamSpec("value", Kind.LITERAL),),
        )
    }

    def resolve_action(self, action_text: Any, *, pointer: str = "") -> str:
        del action_text, pointer  # single action: the chain omits the action slot
        return _CONST_ACTION

    def evaluate(self, call: Call) -> Outcome:
        return Ok(call.params["value"])
