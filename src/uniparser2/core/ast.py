"""Canonical model of stages and compile products (design doc 02 §1, 03 §2).

This module only handles **shape**: stage parsing, serialization round-trip, and the parameter
carriers (``Lit`` / ``Ref``). Every validity check (operator exists, action is legal, parameter
kind) lives in ``core.compile``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from .errors import Up2Error, diag
from .values import dumps_json, loads_json

MIN_STAGE_LEN = 1
MAX_STAGE_LEN = 3
REF_OPERATOR = "$"
TRY_OPERATOR = "try"
"""The operator name of the **guard directive** (change `public-scope-and-try`).

``try`` is not an operator: it changes what the evaluator does with the **next** stage's outcome, so
the operators stay pure. The compiler recognises it as a stage shape, and the evaluator reads it.
"""
"""The operator slot a **whole-chain reference** carries in the serializable source (`03` §2).

A chain written as a string beginning with ``$`` has no operator of its own; this marker is what
``dumps`` writes back for it (``"$in"``), so a compiled chain stays a fixed point. It is never a
registered name, so it can never be reached through the operator lookup.
"""


@dataclass(frozen=True, slots=True)
class Ref:
    """Reference (``$<root>[.<segment>]...``). The shape is here; validity is at compile time."""

    root: str
    path: tuple[str, ...]
    raw: str

    def __str__(self) -> str:
        return self.raw


@dataclass(frozen=True, slots=True)
class Lit:
    """Literal (including the result of a ``{"$lit": v}`` escape)."""

    value: Any


type Param = Lit | Ref | list[Param] | dict[str, Param] | dict[str, CompiledField] | CompiledField
"""Parameter carrier: scalars are ``Lit``/``Ref``; containers are walked recursively (02 §4).

The last member is the **structured** carrier: a compiled field map (``each``'s argument), whose
values are chains rather than other carriers.
"""


@dataclass(frozen=True, slots=True)
class Stage:
    """The **raw slots** of one stage: ``[operator]``, ``[operator, parameter]`` or
    ``[operator, action, parameter]`` (design doc 02 §1).

    Slot 2 is the action for a multi-action operator and the parameter for a single-action one;
    slot 3 is the parameter. A parameter slot is **omitted** — never written empty — when the
    action has nothing left to require, so a stage can be one slot long (``["json"]``) and the
    maximum is three. This class keeps only the raw text and the length; semantics are left to
    compile time (``compile_stage`` reads them through ``Op.action_slot`` / ``Op.param_slot``).

    ``length`` records the **raw array length** (1, 2 or 3); serialization must restore it exactly,
    otherwise the round-trip does not hold.
    """

    op: str
    slot1: Any
    slot2: Any
    length: int = MAX_STAGE_LEN

    def to_list(self) -> list[Any]:
        if self.length == 1:
            return [self.op]
        if self.length == 2:
            return [self.op, self.slot1]
        return [self.op, self.slot1, self.slot2]


@dataclass(frozen=True, slots=True)
class CompiledStage:
    """A compiled stage: action canonicalized, parameters resolved by kind, payload precompiled."""

    index: int
    stage: Stage
    op_name: str
    action: str
    params: dict[str, Param]
    payload: Any = None

    @property
    def pointer(self) -> str:
        return f"/{self.index}"


@dataclass(frozen=True, slots=True)
class CompiledField:
    """One field chain (the smallest executable unit in L1).

    ``name`` is the field-map key this chain was compiled as, or ``""`` for a top-level chain. It is
    what the trace reports as ``field`` (`06` §5.1), so a missing ``title`` inside an ``each`` field
    map is distinguishable from a missing ``price`` inside the same map.

    ``stages`` is empty exactly when the chain was written as a **whole-chain reference**: a string
    beginning with ``$`` means "the value the reference names, unchanged" (`03` §2), so it carries
    no stage at all. That is the only way to express identity -- no one-element stage form exists.
    """

    stages: tuple[CompiledStage, ...]
    source: tuple[Stage, ...]
    name: str = ""
    ref: Ref | None = None
    """Set when the chain **is** one reference: it carries no stage and resolves to that value."""

    def dumps(self) -> str:
        return _dumps_lists(_as_lists(self.source))


def parse_stage(raw: Any, /, *, pointer: str = "") -> Stage:
    """Parse a raw JSON value into a ``Stage``; a shape mismatch is ``UP2-E1004``."""
    if not isinstance(raw, (list, tuple)):
        raise Up2Error(
            diag(
                "UP2-E1004",
                f"a stage must be an array, got {type(raw).__name__}",
                fix='write ["operator", action, parameter], e.g. ["py", "strip"] or ["json"]',
                pointer=pointer,
            )
        )
    length = len(raw)
    if not (MIN_STAGE_LEN <= length <= MAX_STAGE_LEN):
        raise Up2Error(
            diag(
                "UP2-E1004",
                f"stage length is {length}, only 1 to 3 is allowed",
                fix='follow the declared arity: 3 slots is ["operator", action, parameter]; '
                '2 slots is ["operator", parameter] or ["operator", action]; '
                "1 slot is a single-action operator whose parameter is omitted",
                pointer=pointer,
            )
        )
    op = raw[0]
    if not isinstance(op, str):
        raise Up2Error(
            diag(
                "UP2-E1004",
                f"stage slot 1 must be an operator name (str), got {type(op).__name__}",
                fix='write the operator name first, for example "css" / "re" / "py"',
                pointer=f"{pointer}/0",
            )
        )
    action = raw[1] if length >= 2 else None
    value = raw[2] if length == MAX_STAGE_LEN else None
    return Stage(op=op, slot1=action, slot2=value, length=length)


def dumps(stages: Any) -> str:
    """Canonical serialization (compact, non-ASCII not escaped).

    ``dumps(loads(dumps(x))) == dumps(x)`` holds character by character.
    """
    return _dumps_lists(_as_lists(stages))


_CHAIN_TEXT: Final = "the chain text"
"""The noun the strict-text diagnostics name: every stage of a chain arrives as chain text."""


def _dumps_lists(stages: list[list[Any]]) -> str:
    """The one JSON writing of an already-converted stage list.

    Delegates to the strict writer: ``allow_nan=False``, because the chain's own contract is "the
    chain is data".
    """
    return dumps_json(stages, separators=(",", ":"), subject="the chain")


def loads(source: Any, *, pointer: str = "") -> tuple[Stage, ...]:
    """Accept a JSON string / stage array / field-chain array, always return ``tuple[Stage, ...]``.

    The three input forms are idempotent. ``pointer`` is the JSON Pointer prefix of the chain, so a
    sub-chain reports the location it really occupies. Text is read **strictly**: a malformed
    document is ``UP2-E1004`` like any other bad chain, not a decoder exception.
    """
    if isinstance(source, (str, bytes)):
        source = loads_json(source, subject=_CHAIN_TEXT)
    stages = _split_stages(source, pointer=pointer)
    return tuple(parse_stage(raw, pointer=f"{pointer}/{index}") for index, raw in enumerate(stages))


def _as_lists(stages: Any) -> list[list[Any]]:
    if isinstance(stages, CompiledField):
        return [_stage_list(stage) for stage in stages.source]
    out: list[list[Any]] = []
    for item in stages:
        out.append(_stage_list(item) if isinstance(item, Stage) else list(item))
    return out


def _stage_list(stage: Stage) -> list[Any]:
    """One stage of a compiled source; a whole-chain reference writes back as its own text."""
    if stage.op != REF_OPERATOR:
        return stage.to_list()
    slot = stage.slot1
    return [REF_OPERATOR, slot.raw if isinstance(slot, Ref) else str(slot)]


def _split_stages(source: Any, *, pointer: str = "") -> list[Any]:
    """Tell a single stage (``["py","strip"]``) apart from a field chain (``[["py","strip"]]``)."""
    if not isinstance(source, (list, tuple)):
        raise Up2Error(
            diag(
                "UP2-E1004",
                f"a chain must be an array, got {type(source).__name__}",
                fix='pass a single stage ["py","strip"], or a field chain [["py","strip"]]',
                pointer=pointer,
            )
        )
    if not source:
        raise Up2Error(
            diag(
                "UP2-E1004",
                "the chain is empty",
                fix="write at least one stage",
                pointer=pointer,
            )
        )
    first = source[0]
    if isinstance(first, Stage):
        return list(source)
    if isinstance(first, str):
        return [list(source)]
    return list(source)
