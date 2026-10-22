"""The trace: one event per evaluated stage, plus one per effect suspension (`06` §5.1, `03` §4.4).

A trace is a **debugging aid**, not the replay format (`03` §13 O6): what makes a run replayable is
the host's own log of the answers it sent, while a trace is lossy by construction — every value is
replaced by ``type`` / ``preview`` / ``size`` and the whole value is fetched by ``seq`` from this
object's memory, which lives exactly as long as the trace does.

Nothing is collected unless a caller asks for a trace: ``eval_field(..., trace=...)`` and
``start(bundle, value, trace=...)`` are the two injection points, and a run without one behaves
exactly as it did before (`stamp(None)` reads no clock).

The event's ``item`` is the fan-out index, and it has two sources because a story fans out in two
places: the scope of one `each` iteration carries the element's position (the operator hands it over
when it asks for that scope), and the story layer numbers the answers of a `RequestBatch` fan-out.
When both are active the innermost index wins — the event is about the field chain that is running.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from .ast import CompiledField, CompiledStage, Lit, Param, Ref
from .errors import Failed, Missing, Ok, Outcome
from .refs import Scope
from .values import MISSING, JsonValue, is_json_value, text_of, truncate, type_name

PREVIEW_LIMIT: Final = 200
"""How much of a value an event carries; the whole value is fetched with :meth:`Trace.get_value`."""

STATE_OK: Final = "Ok"
STATE_MISSING: Final = "Missing"
STATE_FAILED: Final = "Failed"

EFFECT_REQUEST: Final = "request"
EFFECT_BATCH: Final = "batch"
EFFECT_CALL: Final = "call"

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
    """One row of the trial bench's table (`06` §5.1): a stage, or a suspension.

    ``effect`` is set on a suspension event (``request`` / ``batch`` / ``call``) and left out of the
    JSON for a stage event, which is the shape `06` §5.1 documents.
    """

    seq: int
    step: str | None
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
    effect: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """The event as JSON data (``up2 trial --trace --json``)."""
        payload: dict[str, Any] = {
            "seq": self.seq,
            "step": self.step,
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
        if self.effect is not None:
            payload["effect"] = self.effect
        return payload


class Trace:
    """The events of one run, and the values their previews stand for (`06` §5.1).

    The recording methods are the kernel's own writers: the evaluator calls :meth:`stage` per
    evaluated stage, the story layer calls :meth:`enter` per step and :meth:`effect` per suspension.
    """

    __slots__ = ("_events", "_field", "_item", "_step", "_values")

    def __init__(self) -> None:
        self._events: list[TraceEvent] = []
        self._values: dict[int, dict[str, Any]] = {}
        self._step: str | None = None
        self._field: str | None = None
        self._item: int | None = None

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

    def enter(self, step: str, /, *, item: int | None = None) -> None:
        """Point the trace at the step the events that follow belong to (clears the field)."""
        self._step, self._field, self._item = step, None, item

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
    ) -> None:
        """Record one evaluated stage, with the fan-out index of the scope it ran in."""
        state, detail = _state_of(outcome)
        self._emit(
            step=self._step,
            item=scope.iteration if scope.iteration is not None else self._item,
            field=field,
            stage=stage.index,
            op=stage.op_name,
            action=stage.action,
            params=compiled_params(stage.params),
            incoming=incoming,
            outgoing=_produced(outcome),
            state=state,
            detail=detail,
            ms=ms,
        )

    def effect(
        self,
        kind: str,
        /,
        *,
        step: str,
        incoming: Any,
        handed_out: Any,
        ms: float,
        action: str | None = None,
        params: Mapping[str, Param] | None = None,
    ) -> None:
        """Record one suspension: what the step received, and what the kernel handed the host.

        A suspension is not an error (`03` §5), so its state is ``Ok`` and its kind travels in
        ``effect``: a request, a batch of tasks, or a host function with the arguments it receives.
        """
        self._emit(
            step=step,
            item=self._item,
            field=None,
            stage=None,
            op=None,
            action=action,
            params=None if params is None else compiled_params(params),
            incoming=incoming,
            outgoing=handed_out,
            state=STATE_OK,
            detail=None,
            ms=ms,
            effect=kind,
        )

    def _emit(
        self,
        *,
        step: str | None,
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
        effect: str | None = None,
    ) -> None:
        seq = len(self._events) + 1
        self._events.append(
            TraceEvent(
                seq=seq,
                step=step,
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
                effect=effect,
            )
        )
        self._values[seq] = {INPUT_SIDE: incoming, OUTPUT_SIDE: outgoing}


def _state_of(outcome: Outcome) -> tuple[str, dict[str, str] | None]:
    """A stage's state, and the code and reason a failure carries (`06` §5.1's ``detail``)."""
    if isinstance(outcome, Failed):
        return STATE_FAILED, {"code": outcome.code, "reason": outcome.reason}
    if isinstance(outcome, Missing):
        return STATE_MISSING, None
    return STATE_OK, None


def _produced(outcome: Outcome) -> Any:
    """What a stage's event shows as its output: the value it produced, else the missing sentinel.

    A `Missing` and a `Failed` stage both produced **no value** (`01` §4): the state says which, a
    failure carries its code and reason in ``detail``, and the output stays the sentinel rather than
    inventing a value that the chain never had.
    """
    return outcome.value if isinstance(outcome, Ok) else MISSING


def compiled_params(params: Mapping[str, Param]) -> JsonValue:
    """The **compiled** named parameters as chain data (`06` §5.1): what the engine understood."""
    return {str(key): _param_json(item) for key, item in params.items()}


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
    "EFFECT_BATCH",
    "EFFECT_CALL",
    "EFFECT_REQUEST",
    "INPUT_SIDE",
    "OUTPUT_SIDE",
    "PREVIEW_LIMIT",
    "STATE_FAILED",
    "STATE_MISSING",
    "STATE_OK",
    "Trace",
    "TraceEvent",
    "ValueView",
    "compiled_params",
    "elapsed_ms",
    "stamp",
    "value_view",
]
