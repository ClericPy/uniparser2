"""Chain evaluation: the tri-state short-circuit (design doc 01 §4, 02 §5).

The semantics in one sentence: ``Ok`` continues; ``Missing`` short-circuits the current field and
stays missing (the value is not there); ``Failed`` stops the chain and is reported with its code.
An action that declares ``accepts_missing`` (``py.default``, for example) can catch the ``MISSING``
sentinel as input; that is the only exception to the short-circuit rule.

A caller may pass a ``trace`` (`06` §5.1): then every **evaluated** stage records one event. A stage
the short-circuit skips records nothing, so the last event of a chain is the stage that ended it.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, Final

from . import registry
from .ast import CompiledField, CompiledStage, Lit, Param, Ref
from .errors import Failed, Missing, Ok, Outcome
from .refs import Scope
from .trace import Trace, elapsed_ms, stamp
from .values import MISSING

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

    Nothing settles a missing or a failed value: the outcome is returned as it stands, so the caller
    drops a missing field from its product and stops on a failure. ``trace`` collects one event per
    evaluated stage; without it nothing is measured or recorded.
    """
    active_scope = scope if scope is not None else Scope()
    run_chain = _subchain_runner(trace)
    current: Outcome = Ok(value)
    for stage in compiled.stages:
        if isinstance(current, Failed):
            return current
        if isinstance(current, Missing):
            if not stage.accepts_missing:
                return current
            incoming: Any = MISSING
        else:
            incoming = current.value
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
            )
    return current


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
    resolved = resolve_params(stage.params, scope)
    if isinstance(resolved, (Ok, Missing, Failed)):
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


def resolve_params(params: Mapping[str, Param], scope: Scope) -> Mapping[str, Any] | Outcome:
    """Read the references in the parameter tree into values.

    Any reference that is not ``Ok`` short-circuits the whole stage. This is also how the story
    layer resolves a ``call`` step's ``with`` arguments: the same leaves, the same scope.
    """
    try:
        return {key: _resolve_value(item, scope) for key, item in params.items()}
    except _UnwindError as unwind:
        return unwind.outcome


def _resolve_value(node: Any, scope: Scope) -> Any:
    if isinstance(node, Ref):
        outcome = scope.read(node)
        if isinstance(outcome, Ok):
            return outcome.value
        raise _UnwindError(outcome)
    if isinstance(node, Lit):
        return node.value
    if isinstance(node, list):
        return [_resolve_value(item, scope) for item in node]
    if isinstance(node, dict):
        return {key: _resolve_value(item, scope) for key, item in node.items()}
    return node


class _UnwindError(Exception):
    """Internal signal: on a failed reference, throw the tri-state result up to ``eval_field``."""

    def __init__(self, outcome: Outcome) -> None:
        super().__init__("param unwind")
        self.outcome = outcome
