"""Chain evaluation: a value or a failure (design doc 01 §4, 02 §5).

The semantics in one sentence: ``Ok`` continues; ``Failed`` stops the chain and is reported with its
code. There is no third outcome: a query that matched nothing is ``Ok`` carrying the empty value of
its shape (``empty-value-semantics``).

A caller may pass a ``trace`` (`06` §5.1): then every **evaluated** stage records one event. A
stage a failure stopped the chain before records nothing, so the last event of a chain is the stage
that ended it.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, Final

from . import registry
from .ast import REF_OPERATOR, TRY_OPERATOR, CompiledField, CompiledStage, Lit, Param, Ref, Stage
from .errors import Failed, Ok, Outcome
from .refs import OBJ_ROOT, Scope
from .trace import Trace, elapsed_ms, stamp

logger = logging.getLogger("uniparser2")

_SYSTEM_ERRORS: Final = (KeyboardInterrupt, SystemExit, MemoryError, OSError)


def eval_field(
    compiled: CompiledField,
    value: Any,
    /,
    *,
    scope: Scope | None = None,
    trace: Trace | None = None,
) -> Outcome:
    """Evaluate one field chain stage by stage.

    The outcome is returned as it stands: every field yields a value or the chain stops on a
    failure. ``trace`` collects one event per evaluated stage; without it nothing is measured or
    recorded.

    A chain written as a **whole-chain reference** carries no stage and does no work (`03` §2): the
    outcome is the reference's own read, unchanged, and no event is recorded for it -- the trace's
    stage rows are operators, and a step's product still shows the value that came out.
    """
    active_scope = scope if scope is not None else Scope()
    run_chain = _subchain_runner(trace)
    current: Outcome = Ok(value)
    policy: str | None = None
    """The guard the last ``try`` directive armed; it covers **one** stage and is then gone."""
    if compiled.ref is not None:
        # A chain that **is** a whole-chain reference (`03` §2): the value it names, unchanged, and
        # no stage event -- the trace's stage rows are operators, and the reference does no work.
        current = active_scope.read(compiled.ref)
    elif compiled.source and _is_ref_marker(compiled.source[0]):
        # A chain that only **opens** with one (`["$in", ["py","getattr","url"]]`): the stages below
        # keep their own positions in the source, so the marker is counted but not evaluated.
        current = active_scope.read(compiled.source[0].slot1)
    for index, stage in enumerate(compiled.stages):
        if isinstance(current, Failed):
            return current
        incoming: Any = current.value
        if stage.op_name == TRY_OPERATOR:
            # The directive itself does no work: it arms the guard for the next stage.
            policy = stage.action
            continue
        armed = policy
        policy = None  # the guard covers exactly one stage, success or failure
        started_at = stamp(trace)
        current = _invoke(stage, incoming, active_scope, run_chain)
        if trace is not None:
            trace.stage(
                stage,
                field=compiled.name or None,
                incoming=incoming,
                outcome=current,
                scope=active_scope,
                ms=elapsed_ms(started_at),
                position=index + _marker_offset(compiled),
            )
        if armed is not None and isinstance(current, Failed):
            if armed == "skip":
                # Keep the value the chain already carried, and carry on with the next stage.
                current = Ok(incoming)
                continue
            if armed == "break":
                return Ok(incoming)
    return current


def _marker_offset(compiled: CompiledField) -> int:
    """How many whole-chain reference markers precede this chain's stages in its own source."""
    return 1 if _opening_marker(compiled) else 0


def _opening_marker(compiled: CompiledField) -> bool:
    """Whether the chain opens with a whole-chain reference marker instead of an operator."""
    return bool(compiled.source) and _is_ref_marker(compiled.source[0])


def _is_ref_marker(stage: Any) -> bool:
    """Whether a source stage is the marker of a whole-chain reference (`03` §2)."""
    return isinstance(stage, Stage) and stage.op == REF_OPERATOR


def _subchain_runner(trace: Trace | None) -> registry.ChainRunner:
    """How a structural operator evaluates a compiled sub-chain (design D2 of the L2 change).

    A sub-chain is an ordinary field chain, so ``each`` applies the same rule per element instead of
    inventing one of its own -- and it is traced like one, with the element's own scope (hence its
    fan-out index) and the name the field map compiled the sub-chain as.
    """

    def run(chain: CompiledField, value: Any, scope: Scope) -> Outcome:
        return eval_field(chain, value, scope=scope, trace=trace)

    return run


def _invoke(
    stage: CompiledStage,
    value: Any,
    scope: Scope,
    run_chain: registry.ChainRunner,
) -> Outcome:
    instance = registry.get(stage.op_name)
    if instance is None:  # pragma: no cover - compile time already guarantees it exists
        return Failed(
            code="UP2-E1001",
            reason=f"operator {stage.op_name!r} is not registered",
            fix="import uniparser2.ops again to register the built-in operators",
        )
    resolved = resolve_params(stage.params, scope, value)
    if isinstance(resolved, (Ok, Failed)):
        return resolved
    call = registry.Call(
        value=value,
        action=stage.action,
        params=resolved,
        payload=stage.payload,
        scope=scope,
        run_chain=run_chain,
        cache=scope.materializer,
    )
    try:
        return instance.evaluate(call)
    except _SYSTEM_ERRORS:
        raise
    except Exception as exc:
        logger.warning("operator %s raised an unexpected exception: %r", stage.op_name, exc)
        return Failed(
            code="UP2-E2099",
            reason=f"{stage.op_name}.{stage.action} raised an unexpected exception: {exc!r}",
            fix="this is a defect in the operator implementation; keep the chain and input to "
            "reproduce it",
        )


_NO_STAGE_VALUE: Final = object()
"""Marks "no stage value here": a read of ``$obj`` then fails instead of yielding a value."""


def resolve_params(
    params: Mapping[str, Param], scope: Scope, value: Any = _NO_STAGE_VALUE
) -> Mapping[str, Any] | Outcome:
    """Read the references in the parameter tree into values.

    ``value`` is the value the stage received, which is what ``$obj`` names; the story layer
    resolves a ``call`` step's ``with`` arguments without one, so ``$obj`` is a coded failure there.
    Any reference that is not ``Ok`` short-circuits the whole stage.
    """
    try:
        return {key: _resolve_value(item, scope, value) for key, item in params.items()}
    except _UnwindError as unwind:
        return unwind.outcome


def _resolve_value(node: Any, scope: Scope, value: Any = _NO_STAGE_VALUE) -> Any:
    if isinstance(node, Ref):
        if node.root == OBJ_ROOT:
            if value is _NO_STAGE_VALUE:
                raise _UnwindError(
                    Failed(
                        code="UP2-E2001",
                        reason="$obj names the value a stage received, and this is not a stage",
                        fix='a call step argument reads a scope; use "$in" / "$locals" there',
                    )
                )
            return value
        outcome = scope.read(node)
        if isinstance(outcome, Ok):
            return outcome.value
        raise _UnwindError(outcome)
    if isinstance(node, Lit):
        return node.value
    if isinstance(node, list):
        return [_resolve_value(item, scope, value) for item in node]
    if isinstance(node, dict):
        return {key: _resolve_value(item, scope, value) for key, item in node.items()}
    return node


class _UnwindError(Exception):
    """Internal signal: on a failed reference, throw the tri-state result up to ``eval_field``."""

    def __init__(self, outcome: Outcome) -> None:
        super().__init__("param unwind")
        self.outcome = outcome
