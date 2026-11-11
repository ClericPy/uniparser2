"""The trace: one event per evaluated stage (design doc 06 §5.1, 03 §5.4).

A trace is a **debugging aid**, not the replay format (`03` §13): what makes a run replayable is the
host's own log of what its udfs answered, while a trace is lossy by construction — every value is
replaced by ``type`` / ``preview`` / ``size`` and the whole value is fetched by ``seq`` from this
object's memory, which lives exactly as long as the trace does.

Nothing is collected unless a caller asks for a trace: ``eval_field(..., trace=...)`` and
``run(..., trace=...)`` are the two injection points, and a run without one behaves exactly as it
did before (`stamp(None)` reads no clock).

The event's ``item`` is the fan-out index: the scope of one `each` iteration carries the element's
position, which the operator hands over when it asks for that scope. A node call enters the callee's
name for its stages and restores the caller's on return.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from .ast import CompiledField, CompiledStage, Lit, Param, Ref
from .errors import Failed, Ok, Outcome
from .refs import Scope
from .values import JsonValue, is_json_value, text_of, truncate, type_name

PREVIEW_LIMIT: Final = 200
"""How much of a value an event carries; the whole value is fetched with :meth:`Trace.get_value`."""

STATE_OK: Final = "Ok"
STATE_FAILED: Final = "Failed"

INPUT_SIDE: Final = "input"
OUTPUT_SIDE: Final = "output"


@dataclass(frozen=True, slots=True)
class ValueView:
    """What an event carries instead of a value: its type, a truncated preview and its size."""

    type: str
    preview: str
    size: int

    def to_dict(self) -> dict[str, Any]:
        """The view as JSON data."""
        return {"type": self.type, "preview": self.preview, "size": self.size}


def value_view(value: object) -> ValueView:
    """One value as a trace carries it: the type name, the first 200 characters, the full size.

    The display text is rendered **once**: the preview is its head and ``size`` is its length.
    """
    text = text_of(value)
    return ValueView(type=type_name(value), preview=truncate(text, PREVIEW_LIMIT), size=len(text))


def stamp(trace: Trace | None) -> float:
    """A start stamp for a measurement the trace keeps; ``0.0`` when nothing is traced."""
    return 0.0 if trace is None else time.perf_counter()


def elapsed_ms(started_at: float) -> float:
    """Milliseconds since a :func:`stamp`, rounded for reading; ``0.0`` for an untraced run."""
    return 0.0 if started_at == 0.0 else round((time.perf_counter() - started_at) * 1000, 3)


@dataclass(frozen=True, slots=True)
class TraceEvent:
    """One row of the trial bench's table (`06` §5.1): one evaluated stage."""

    seq: int
    node: str | None
    item: int | None
    field: str | None
    stage: int | None
    op: str | None
    action: str | None
    params: JsonValue | None
    input: ValueView
    output: ValueView
    state: str
    detail: dict[str, str] | None
    ms: float

    def to_dict(self) -> dict[str, Any]:
        """The event as JSON data (``up2 trial --trace --json``)."""
        return {
            "seq": self.seq,
            "node": self.node,
            "item": self.item,
            "field": self.field,
            "stage": self.stage,
            "op": self.op,
            "action": self.action,
            "params": self.params,
            "input": self.input.to_dict(),
            "output": self.output.to_dict(),
            "state": self.state,
            "detail": self.detail,
            "ms": self.ms,
        }


class Trace:
    """The events of one run, and the values their previews stand for (`06` §5.1).

    The recording methods are the kernel's own writers: the evaluator calls :meth:`stage` per
    evaluated stage, and the story layer calls :meth:`enter` / :meth:`leave` around a node call.
    """

    __slots__ = ("_events", "_field", "_item", "_node", "_stack", "_values")

    def __init__(self) -> None:
        self._events: list[TraceEvent] = []
        self._values: dict[int, dict[str, Any]] = {}
        self._node: str | None = None
        self._field: str | None = None
        self._item: int | None = None
        self._stack: list[tuple[str | None, str | None, int | None]] = []

    def __len__(self) -> int:
        return len(self._events)

    @property
    def events(self) -> tuple[TraceEvent, ...]:
        """Every event, in evaluation order."""
        return tuple(self._events)

    def to_list(self) -> list[dict[str, Any]]:
        """Every event as JSON data."""
        return [event.to_dict() for event in self._events]

    def get_value(self, seq: int, /, *, side: str = OUTPUT_SIDE) -> Any:
        """The whole value a preview stands for: the event's output, or its input with ``side``.

        The value the trace previewed is what it kept, so a large document is read here rather than
        travelling through the event list.
        """
        return self._values[seq][side]

    # ------------------------------------------------------------ recording

    def enter(self, node: str, /, *, item: int | None = None) -> None:
        """Point the trace at the node the events that follow belong to (clears the field)."""
        self._stack.append((self._node, self._field, self._item))
        self._node, self._field, self._item = node, None, item

    def leave(self) -> None:
        """Restore the node the trace was pointing at before the matching :meth:`enter`."""
        if self._stack:
            self._node, self._field, self._item = self._stack.pop()

    def stage(
        self,
        stage: CompiledStage,
        /,
        *,
        field: str | None,
        incoming: Any,
        outcome: Outcome,
        scope: Scope,
        ms: float,
        position: int | None = None,
    ) -> None:
        """Record one evaluated stage, with the fan-out index of the scope it ran in."""
        state, detail = _state_of(outcome)
        self._emit(
            node=self._node,
            item=scope.iteration if scope.iteration is not None else self._item,
            field=field,
            stage=stage.index if position is None else position,
            op=stage.op_name,
            action=stage.action,
            params=compiled_params(stage.params),
            incoming=incoming,
            outgoing=_produced(outcome),
            state=state,
            detail=detail,
            ms=ms,
        )

    def _emit(
        self,
        *,
        node: str | None,
        item: int | None,
        field: str | None,
        stage: int | None,
        op: str | None,
        action: str | None,
        params: JsonValue | None,
        incoming: Any,
        outgoing: Any,
        state: str,
        detail: dict[str, str] | None,
        ms: float,
    ) -> None:
        seq = len(self._events) + 1
        self._events.append(
            TraceEvent(
                seq=seq,
                node=node,
                item=item,
                field=field,
                stage=stage,
                op=op,
                action=action,
                params=params,
                input=value_view(incoming),
                output=value_view(outgoing),
                state=state,
                detail=detail,
                ms=ms,
            )
        )
        self._values[seq] = {INPUT_SIDE: incoming, OUTPUT_SIDE: outgoing}


def _state_of(outcome: Outcome) -> tuple[str, dict[str, str] | None]:
    """A stage's state, and the code and reason a failure carries (`06` §5.1's ``detail``)."""
    if isinstance(outcome, Failed):
        return STATE_FAILED, {"code": outcome.code, "reason": outcome.reason}
    return STATE_OK, None


def _produced(outcome: Outcome) -> Any:
    """What a stage's event shows as its output: the value it produced.

    A failed stage produced **no value** (`01` §4): the state says so, the failure carries its code
    and reason in ``detail``, and the output is ``None`` rather than an invented value.
    """
    return outcome.value if isinstance(outcome, Ok) else None


def compiled_params(params: Mapping[str, Param]) -> JsonValue:
    """The **compiled** named parameters as chain data (`06` §5.1): what the engine understood."""
    return {str(key): _param_json(item) for key, item in params.items()}


def _chain_json(node: CompiledField) -> JsonValue:
    """One compiled chain: its stages, in source order (`06` §5.1)."""
    return {
        "kind": "chain",
        "stages": [
            {
                "op": stage.op_name,
                "action": stage.action,
                "params": compiled_params(stage.params),
            }
            for stage in node.stages
        ],
    }


def _param_json(node: Any) -> JsonValue:
    """One compiled parameter: a leaf says what it is, a container is walked."""
    if isinstance(node, Ref):
        # The reference's own text without the `$`: `06` §5.1 writes the target as a path.
        return {"kind": "ref", "target": ".".join((node.root, *node.path))}
    if isinstance(node, Lit):
        value: JsonValue = node.value if is_json_value(node.value) else text_of(node.value)
        return {"kind": "lit", "value": value}
    if isinstance(node, CompiledField):
        return _chain_json(node)
    if isinstance(node, Mapping):
        if any(isinstance(item, CompiledField) for item in node.values()):
            fields = {str(key): _param_json(item) for key, item in node.items()}
            return {"kind": "fields", "fields": fields}
        return {str(key): _param_json(item) for key, item in node.items()}
    if isinstance(node, (list, tuple)):
        return [_param_json(item) for item in node]
    return node if is_json_value(node) else text_of(node)


__all__ = [
    "INPUT_SIDE",
    "OUTPUT_SIDE",
    "PREVIEW_LIMIT",
    "STATE_FAILED",
    "STATE_OK",
    "Trace",
    "TraceEvent",
    "ValueView",
    "compiled_params",
    "elapsed_ms",
    "stamp",
    "value_view",
]
