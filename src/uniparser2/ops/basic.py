"""Building-block operators: ``const`` (design doc 02 §6.5) and ``each`` (design doc 03 §4).

Two-slot operators ``[const, value]`` / ``[each, fields]``: each has **exactly one action**, so the
chain omits the action slot.

Type conversion (the former ``cast`` operator) has been folded back into ``py``: ``str`` / ``int`` /
``float`` / ``bool`` / ``list`` / ``from_json`` — these are Python built-ins to begin with, and a
standalone operator would only add another "where does the target type go" convention (see D-02-14
in ``02``).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar, Final

from ..core.ast import CompiledField, Param
from ..core.errors import Failed, Missing, Ok, Outcome
from ..core.limits import MAX_EACH_ITER
from ..core.registry import ActionSpec, Call, Kind, Op, ParamSpec, op
from ..core.values import type_name

_CONST_ACTION: Final = "const"
_EACH_ACTION: Final = "each"
_LOCAL_PREFIX: Final = "_"


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


@op("each")
class Each(Op):
    """Run a field map once per element of the list the stage above produced.

    ``["each", {"title": [["css1","text","a"]]}]`` yields one dictionary per element, in input
    order. Each element is evaluated in **its own scope**, so a field can stash a temporary in
    ``locals`` and a later field of the same element can read it; a field whose name starts with
    ``_`` is such a temporary and never becomes a key of the element's dictionary.

    The input must be a list: an element of an object would be a key/value pair, and no operator in
    the set can consume one (``py.getitem`` takes lists). An empty list yields an empty list.
    """

    summary = "One dictionary per element of a list"
    arity = 2
    slot_roles = ("fields",)
    actions: ClassVar[Mapping[str, ActionSpec]] = {
        _EACH_ACTION: ActionSpec(
            _EACH_ACTION,
            "Run the field map once per element",
            (ParamSpec("fields", Kind.FIELDS),),
        )
    }

    def resolve_action(self, action_text: Any, *, pointer: str = "") -> str:
        del action_text, pointer  # single action: the chain omits the action slot
        return _EACH_ACTION

    def precompile(self, action: str, params: Mapping[str, Param], *, pointer: str = "") -> Any:
        del action, pointer  # the compiled field map is the payload the runtime needs
        return params["fields"]

    def evaluate(self, call: Call) -> Outcome:
        value = call.value
        if not isinstance(value, list):
            return Failed(
                code="UP2-E2002",
                reason=f"each needs a list, got {type_name(value)}",
                fix='take a list out of it first: ["css","nodes","li"] for nodes, '
                '["py","list"] for JSON array text, ["py","get",K] for one key of an object',
            )
        if len(value) > MAX_EACH_ITER:
            return Failed(
                code="UP2-E2012",
                reason=f"each got {len(value)} elements, over MAX_EACH_ITER={MAX_EACH_ITER}",
                fix='truncate the list first with ["py","slice",":100"]',
            )
        fields: Mapping[str, CompiledField] = call.payload
        rows: list[dict[str, Any]] = []
        for element in value:
            scope = call.scope.child()
            row: dict[str, Any] = {}
            for name, chain in fields.items():
                outcome = call.run_chain(chain, element, scope)
                if isinstance(outcome, Failed):
                    return outcome
                if isinstance(outcome, Missing):
                    continue  # an absent field is simply not part of this element
                if name.startswith(_LOCAL_PREFIX):
                    scope.locals[name] = outcome.value
                else:
                    row[name] = outcome.value
            rows.append(row)
        return Ok(rows)
