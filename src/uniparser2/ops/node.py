"""``node`` operator: call another node of the same story (design doc 03 §5.2).

The stage is ``["node", name]``: two slots, one action, the node name in slot 2. The current stage
value becomes the callee's ``$in``, the callee shares the caller's ``$locals`` and ``$public``, and
the caller's ``$in`` is restored when the call returns.

The name is checked against the story's node table at compile time (``UP2-E1016``); a standalone
chain has no table, so it cannot call a node. The call graph's cycles are rejected by the compiler
(``UP2-E1017``).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar, Final

from ..core.ast import Lit, Param
from ..core.errors import Failed, Ok, Outcome
from ..core.registry import ActionSpec, Call, Kind, Op, ParamSpec, op

_NODE_ACTION: Final = "call"


@op("node")
class Node(Op):
    """Call a node of this story with the current value."""

    summary = "Call a node of this story with the current value"
    arity = 2
    slot_roles = ("node",)
    actions: ClassVar[Mapping[str, ActionSpec]] = {
        _NODE_ACTION: ActionSpec(
            _NODE_ACTION,
            "Run the named node",
            (ParamSpec("node", Kind.LITERAL),),
        )
    }

    def resolve_action(self, action_text: Any, *, pointer: str = "") -> str:
        del action_text, pointer  # single action: the stage omits the action slot
        return _NODE_ACTION

    def precompile(self, action: str, params: Mapping[str, Param], *, pointer: str = "") -> Any:
        del action, pointer  # the compiled node name is the payload the runtime needs
        raw = params["node"]
        return raw.value if isinstance(raw, Lit) else raw

    def evaluate(self, call: Call) -> Outcome:
        if call.run_node is None:
            return Failed(
                code="UP2-E1016",
                reason="a node call needs a story; this chain has no node table",
                fix="run the chain through a story node, or inline the callee",
            )
        name = call.payload
        if not isinstance(name, str):
            return Failed(
                code="UP2-E1016",
                reason=f"the node name must be a string, got {type(name).__name__}",
                fix="name a node of this story",
            )
        # The story's runner raises the callee's own diagnostic with the callee's pointer; it must
        # reach the story boundary unchanged. The current scope travels with the call so the
        # callee shares `$locals` and the element's fan-out position.
        return Ok(call.run_node(name, call.value, call.scope))
