"""The ``each`` operator (design doc 03 §4): one pass per element of a list.

``each`` has exactly one action, so the chain writes no action slot and its parameter is slot 2.
The parameter's shape selects the mode — an object is a field map, an array is one chain. The
former ``const`` operator is gone: a literal is ``["py","const",value]`` (design D0).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar, Final

from ..core.ast import CompiledField, Param
from ..core.errors import Failed, Ok, Outcome
from ..core.limits import MAX_EACH_ITER
from ..core.registry import ActionSpec, Call, Kind, Op, ParamSpec, op
from ..core.values import type_name

_EACH_ACTION: Final = "each"
_LOCAL_PREFIX: Final = "_"


@op("each")
class Each(Op):
    """Run a field map once per element of the list the stage above produced.

    ``["each", {"title": [["css1","text","a"]]}]`` yields one dictionary per element, in input
    order. Each element is evaluated in **its own scope**, so a field can stash a temporary in
    ``locals`` and a later field of the same element can read it; a field whose name starts with
    ``_`` is such a temporary and never becomes a key of the element's dictionary.

    The parameter's shape selects the mode: an **object** is a field map, an **array** is one
    chain run over every element, answering a list of its products (``["each",[["py","strip"]]]``).

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
            (ParamSpec("fields", Kind.FIELDS_OR_CHAIN),),
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
                '["py","list"] for JSON array text, ["py","getitem",K] for one key of an object',
            )
        if len(value) > MAX_EACH_ITER:
            return Failed(
                code="UP2-E2012",
                reason=f"each got {len(value)} elements, over MAX_EACH_ITER={MAX_EACH_ITER}",
                fix='truncate the list first with ["py","slice",":100"]',
            )
        if isinstance(call.payload, CompiledField):
            return self._run_chain(call, value)
        fields: Mapping[str, CompiledField] = call.payload
        rows: list[dict[str, Any]] = []
        for position, element in enumerate(value):
            # The element's own position is what the trace reports as the fan-out index (`06` §5.1),
            # and each element gets its own scope so a field can stash a local for a later one.
            scope = call.scope.child(position)
            row: dict[str, Any] = {}
            for name, chain in fields.items():
                outcome = call.run_chain(chain, element, scope)
                if isinstance(outcome, Failed):
                    return outcome
                if name.startswith(_LOCAL_PREFIX):
                    scope.write_local((name,), outcome.value)
                else:
                    row[name] = outcome.value
            rows.append(row)
        return Ok(rows)

    @staticmethod
    def _run_chain(call: Call, value: list[Any]) -> Outcome:
        """The chain mode: one product per element, in input order."""
        chain = call.payload
        products: list[Any] = []
        for position, element in enumerate(value):
            outcome = call.run_chain(chain, element, call.scope.child(position))
            if isinstance(outcome, Failed):
                return outcome
            products.append(outcome.value)
        return Ok(products)
