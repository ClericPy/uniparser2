"""Chain evaluation: tri-state short-circuit plus policy (design doc 01 §4, 02 §5).

The semantics in one sentence: ``Ok`` continues; ``Missing`` short-circuits the current field
(falling to a value according to ``on_missing``); ``Failed`` either stops or degrades according to
``on_error``. An action that declares ``accepts_missing`` (``py.default``, for example) can catch
the ``MISSING`` sentinel as input; that is the only exception to the short-circuit rule.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from . import registry
from .ast import CompiledField, CompiledStage, Lit, Param, Ref
from .errors import Failed, Missing, Ok, Outcome
from .refs import Scope
from .values import MISSING

logger = logging.getLogger("uniparser2")

MISSING_STRATEGIES: Final = ("empty", "none", "drop", "raise")
ERROR_STRATEGIES: Final = ("raise", "empty", "none", "drop")
_SYSTEM_ERRORS: Final = (KeyboardInterrupt, SystemExit, MemoryError, OSError)


@dataclass(frozen=True, slots=True)
class Policy:
    """The handling policy for missing/failed (01 §4.2).

    The default is "missing falls to an empty string, a failure is reported".
    """

    on_missing: str = "empty"
    on_error: str = "raise"

    def __post_init__(self) -> None:
        if self.on_missing not in MISSING_STRATEGIES:
            raise ValueError(
                f"on_missing must be one of {MISSING_STRATEGIES}, got {self.on_missing!r}"
            )
        if self.on_error not in ERROR_STRATEGIES:
            raise ValueError(f"on_error must be one of {ERROR_STRATEGIES}, got {self.on_error!r}")


DEFAULT_POLICY: Final = Policy()


def eval_field(
    compiled: CompiledField,
    value: Any,
    /,
    *,
    scope: Scope | None = None,
    policy: Policy = DEFAULT_POLICY,
) -> Outcome:
    """Evaluate one field chain stage by stage."""
    active_scope = scope if scope is not None else Scope()
    run_chain = _subchain_runner(policy)
    current: Outcome = Ok(value)
    for stage in compiled.stages:
        if isinstance(current, Failed):
            return _degrade_error(current, policy)
        if isinstance(current, Missing):
            if not stage.accepts_missing:
                return _degrade_missing(current, policy)
            current = _invoke(stage, MISSING, active_scope, run_chain)
        else:
            current = _invoke(stage, current.value, active_scope, run_chain)
    if isinstance(current, Failed):
        return _degrade_error(current, policy)
    if isinstance(current, Missing):
        return _degrade_missing(current, policy)
    return current


def _subchain_runner(policy: Policy) -> registry.ChainRunner:
    """How a structural operator evaluates a compiled sub-chain (design D2 of the L2 change).

    The sub-chain is evaluated under the **policy in force** for the chain that owns it, so ``each``
    applies the effective policy per element instead of inventing one of its own.
    """

    def run(chain: CompiledField, value: Any, scope: Scope) -> Outcome:
        return eval_field(chain, value, scope=scope, policy=policy)

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
    resolved = _resolve_params(stage.params, scope)
    if isinstance(resolved, (Ok, Missing, Failed)):
        return resolved
    call = registry.Call(
        value=value,
        action=stage.action,
        params=resolved,
        payload=stage.payload,
        scope=scope,
        run_chain=run_chain,
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


def _resolve_params(params: Mapping[str, Param], scope: Scope) -> Mapping[str, Any] | Outcome:
    """Read the references in the parameter tree into values.

    Any reference that is not ``Ok`` short-circuits the whole stage.
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


def _degrade_missing(missing: Missing, policy: Policy) -> Outcome:
    if policy.on_missing == "raise":
        return Failed(
            code="UP2-E2015",
            reason=missing.reason,
            fix="fix the selector/regex, or change on_missing to empty / none / drop",
        )
    if policy.on_missing == "drop":
        return missing
    return Ok("" if policy.on_missing == "empty" else None)


def _degrade_error(failed: Failed, policy: Policy) -> Outcome:
    if policy.on_error == "raise":
        return failed
    logger.warning("degrading a failure per policy: %s %s", failed.code, failed.reason)
    if policy.on_error == "drop":
        return Missing(reason=failed.reason)
    return Ok("" if policy.on_error == "empty" else None)
