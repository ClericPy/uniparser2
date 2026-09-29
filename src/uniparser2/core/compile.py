"""Compile time: stage validation + parameter schema + precompile (design doc 01 §5, 02 §1-§4, §7).

Compile time **never touches the runtime**: it reads no file, performs no network call, and
evaluates nothing. Structural errors are eliminated here and the runtime only evaluates -- this is
where ``N3``, "a bad chain fails at compile time", lands.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping, Sequence
from enum import StrEnum
from typing import Any

from . import registry
from .ast import CompiledField, CompiledStage, Lit, Param, Ref, Stage, loads, parse_stage
from .errors import Up2Error, diag
from .limits import MAX_STEPS_PER_FIELD
from .refs import LIT_DIRECTIVE, RESERVED_ROOTS, is_ref_text, parse_ref

logger = logging.getLogger("uniparser2")

_DIRECTIVE_PREFIX = "$"
_DEFERRED_ROOTS = ("item",)
_DEFERRED_FIX = "$item is only available inside a $map template (L2); use $locals / $globals"
_NO_PARAM_PLACEHOLDERS = (None, "")


def compile_field(source: Any, /, *, products: Iterable[str] = ()) -> CompiledField:
    """Compile a stage array / field chain / JSON string / compiled field into ``CompiledField``."""
    source_stages = _as_stages(source)
    if len(source_stages) > MAX_STEPS_PER_FIELD:
        raise Up2Error(
            diag(
                "UP2-E1012",
                f"field chain has {len(source_stages)} steps, over "
                f"MAX_STEPS_PER_FIELD={MAX_STEPS_PER_FIELD}",
                fix="split it into several field chains, or fold a piece of logic into a "
                "named operator/udf",
                pointer="",
            )
        )
    declared = tuple(dict.fromkeys(products))
    stages = tuple(
        compile_stage(stage, index=index, products=declared)
        for index, stage in enumerate(source_stages)
    )
    logger.debug("compiled field: steps=%d ops=%s", len(stages), [item.op_name for item in stages])
    return CompiledField(stages=stages, source=source_stages)


def compile_stage(raw: Any, /, *, index: int = 0, products: Iterable[str] = ()) -> CompiledStage:
    """Compile a single stage."""
    pointer = f"/{index}"
    stage = raw if isinstance(raw, Stage) else parse_stage(raw, pointer=pointer)
    instance = registry.get(stage.op)
    if instance is None:
        raise Up2Error(
            diag(
                "UP2-E1001",
                f"unknown operator {stage.op!r}",
                fix="use one of the following operators",
                pointer=f"{pointer}/0",
                allowed=registry.names(),
            )
        )
    action_text = _slot(stage, instance.action_slot)
    _check_arity(instance, stage, pointer=pointer)
    action = instance.resolve_action(action_text, pointer=f"{pointer}/{instance.action_slot}")
    spec = instance.action_spec(action)
    missing = registry.action_missing_deps(instance, action)
    if missing:
        raise Up2Error(
            diag(
                "UP2-E1107",
                f"{instance.name}.{action} is missing dependencies: {', '.join(missing)}",
                fix="install the optional dependency and retry",
                pointer=f"{pointer}/1",
                allowed=registry.install_hints(missing),
            )
        )
    param_slot = instance.param_slot
    params = _build_params(
        spec,
        instance.params_source(action_text, _slot(stage, param_slot)),
        preset=instance.action_params(action, action_text),
        pointer=f"{pointer}/{param_slot}",
    )
    _check_refs(params, products=tuple(products), pointer=f"{pointer}/{param_slot}")
    payload = instance.precompile(action, params, pointer=f"{pointer}/{param_slot}")
    return CompiledStage(
        index=index,
        stage=stage,
        op_name=instance.name,
        action=action,
        params=params,
        accepts_missing=spec.accepts_missing,
        payload=payload,
    )


def _as_stages(source: Any) -> tuple[Stage, ...]:
    if isinstance(source, CompiledField):
        return source.source
    return loads(source)


def _slot(stage: Stage, index: int | None) -> Any:
    """Return one slot's raw text as declared by the operator; ``None`` means no such slot."""
    if index == 1:
        return stage.slot1
    if index == 2:
        return stage.slot2
    return None


def _check_arity(instance: registry.Op, stage: Stage, *, pointer: str) -> None:
    """The stage length must be **exactly** the arity declared by the operator (2 or 3)."""
    if stage.length == instance.arity:
        return
    shape = ", ".join(f"slot{i + 2}={role}" for i, role in enumerate(instance.slot_roles))
    raise Up2Error(
        diag(
            "UP2-E1004",
            f"{stage.op} needs {instance.arity} slots, got {stage.length}",
            fix=f"this operator's slots are {shape}; for an action with no parameters, "
            'write "" in slot 3',
            pointer=pointer,
        )
    )


class _Shape(StrEnum):
    """Shape of the parameter slot (the four shapes of 02 §4 plus three boundary cases)."""

    DEFAULTS = "defaults"
    DIRECTIVE = "directive"
    NO_PARAMS = "no_params"
    SINGLE = "single"
    NAMED = "named"
    POSITIONAL = "positional"
    FIRST = "first"


def _is_empty_placeholder(raw: Any, active: Sequence[registry.ParamSpec]) -> bool:
    """``None``, or an empty string when nothing is required, means "no parameter passed".

    Draft ``04`` writes "no parameters" as an empty-string placeholder (``["py","strip",""]``,
    ``["udf","fn",""]``), so an empty string has to be read as "not passed"; but with **required
    parameters** an empty string is a real value (the empty separator of ``["py","split",""]`` must
    be able to fail at runtime instead of being taken as not passed).
    """
    if raw is None:
        return True
    return raw == "" and not any(param.required for param in active)


def _classify(active: Sequence[registry.ParamSpec], raw: Any) -> _Shape:
    if _is_empty_placeholder(raw, active):
        return _Shape.DEFAULTS
    if isinstance(raw, dict) and _directive_name(raw) is not None:
        return _Shape.DIRECTIVE
    if not active:
        return _Shape.NO_PARAMS
    if len(active) == 1:
        return _Shape.SINGLE
    if isinstance(raw, dict):
        return _Shape.NAMED
    if isinstance(raw, (list, tuple)):
        return _Shape.POSITIONAL
    return _Shape.FIRST


def _first_param(active: Sequence[registry.ParamSpec]) -> registry.ParamSpec:
    """The first parameter still to fill (only called once parameters are known to exist)."""
    first = next(iter(active), None)
    if first is None:  # pragma: no cover - _classify already rejects zero parameters
        raise Up2Error(diag("UP2-E1005", "this action has no parameters", pointer=""))
    return first


def _build_params(
    spec: registry.ActionSpec,
    raw: Any,
    *,
    preset: Mapping[str, Param],
    pointer: str,
) -> dict[str, Param]:
    """The four shapes of the parameter slot -> named parameters (02 §4).

    Classify first, then dispatch: the order of discrimination is fixed and leaves no ambiguity.

    ``preset`` holds the **parameters the action slot already provided** (``css``'s ``@href``
    providing ``attr``, for example); they take no part in the parameter-slot mapping and only join
    the final merge.
    """
    active = tuple(param for param in spec.params if param.name not in preset)
    shape = _classify(active, raw)
    if shape is _Shape.DEFAULTS:
        return _fill_defaults(spec, active, {}, preset=preset, pointer=pointer)
    if shape is _Shape.DIRECTIVE:
        directive = _directive_name(raw) or ""
        return _directive_params(spec, active, raw, directive, preset=preset, pointer=pointer)
    if shape is _Shape.NO_PARAMS:
        raise Up2Error(
            diag(
                "UP2-E1005",
                f"action {spec.name!r} accepts no parameters, but {raw!r} was given",
                fix='drop slot 3, or write "" (the empty placeholder)',
                pointer=pointer,
            )
        )
    if shape is _Shape.SINGLE:
        first = _first_param(active).name
        return _fill_defaults(spec, active, {first: raw}, preset=preset, pointer=pointer)
    if shape is _Shape.NAMED:
        return _named_params(spec, active, raw, preset=preset, pointer=pointer)
    if shape is _Shape.POSITIONAL:
        return _positional_params(spec, active, raw, preset=preset, pointer=pointer)
    # A scalar given to a multi-parameter action lands on the first parameter, and the rest take
    # their defaults (["time","$parse","zh"], for example).
    first = _first_param(active).name
    return _fill_defaults(spec, active, {first: raw}, preset=preset, pointer=pointer)


def _named_params(
    spec: registry.ActionSpec,
    active: Sequence[registry.ParamSpec],
    raw: Mapping[str, Any],
    *,
    preset: Mapping[str, Param],
    pointer: str,
) -> dict[str, Param]:
    declared_names = {param.name for param in active}
    unknown = [key for key in raw if key not in declared_names]
    if unknown:
        raise Up2Error(
            diag(
                "UP2-E1005",
                f"unknown parameters: {', '.join(map(repr, unknown))}",
                fix="use one of the following parameter names, or a positional array",
                pointer=pointer,
                allowed=tuple(param.name for param in active),
            )
        )
    return _fill_defaults(spec, active, dict(raw), preset=preset, pointer=pointer)


def _positional_params(
    spec: registry.ActionSpec,
    active: Sequence[registry.ParamSpec],
    raw: Any,
    *,
    preset: Mapping[str, Param],
    pointer: str,
) -> dict[str, Param]:
    if len(raw) > len(active):
        raise Up2Error(
            diag(
                "UP2-E1005",
                f"{len(raw)} positional parameters were given, the action accepts "
                f"only {len(active)}",
                fix="drop the extra parameters, or use a named object",
                pointer=pointer,
                allowed=tuple(param.name for param in active),
            )
        )
    return _fill_defaults(
        spec,
        active,
        {param.name: value for param, value in zip(active, raw, strict=False)},
        preset=preset,
        pointer=pointer,
    )


def _fill_defaults(
    spec: registry.ActionSpec,
    active: Sequence[registry.ParamSpec],
    values: Mapping[str, Any],
    *,
    preset: Mapping[str, Param],
    pointer: str,
) -> dict[str, Param]:
    """Merge the parameters the action slot provided, fill in defaults, and resolve by kind."""
    params: dict[str, Param] = dict(preset)
    for param in active:
        if param.name in values:
            params[param.name] = _resolve_param(
                param, values[param.name], pointer=f"{pointer}/{param.name}"
            )
        elif param.required:
            raise Up2Error(
                diag(
                    "UP2-E1005",
                    f"missing required parameter {param.name!r}",
                    fix=f"add {param.name} (kind={param.kind})",
                    pointer=pointer,
                    allowed=tuple(item.name for item in active),
                )
            )
        else:
            params[param.name] = Lit(param.default)
    return params


def _resolve_param(spec: registry.ParamSpec, raw: Any, *, pointer: str) -> Param:
    """Resolve by kind; containers are walked recursively (leaves take the same parameter kind)."""
    if spec.kind is registry.Kind.LITERAL:
        return Lit(raw)
    if isinstance(raw, list):
        return [_resolve_param(spec, item, pointer=pointer) for item in raw]
    if isinstance(raw, dict):
        return {key: _resolve_param(spec, item, pointer=pointer) for key, item in raw.items()}
    return _resolve_leaf(spec, raw, pointer=pointer)


def _resolve_leaf(spec: registry.ParamSpec, raw: Any, *, pointer: str) -> Param:
    """A scalar leaf: the kind decides "reference or literal" (02 §3.2/§3.3)."""
    if spec.kind is registry.Kind.REF:
        if not is_ref_text(raw):
            raise Up2Error(
                diag(
                    "UP2-E1007",
                    f"parameter {spec.name!r} must be a reference, got {raw!r}",
                    fix='write a reference such as "$globals.name" / "$locals._tmp"',
                    pointer=pointer,
                )
            )
        return parse_ref(raw, pointer=pointer)
    if is_ref_text(raw):
        # Only REF_OR_LITERAL reaches here: a leading `$` means a reference.
        return parse_ref(raw, pointer=pointer)
    return Lit(raw)


def _directive_name(raw: Mapping[str, Any]) -> str | None:
    if len(raw) != 1:
        return None
    key = next(iter(raw))
    return key if isinstance(key, str) and key.startswith(_DIRECTIVE_PREFIX) else None


def _directive_params(
    spec: registry.ActionSpec,
    active: Sequence[registry.ParamSpec],
    raw: Mapping[str, Any],
    directive: str,
    *,
    preset: Mapping[str, Param],
    pointer: str,
) -> dict[str, Param]:
    if directive != LIT_DIRECTIVE:
        raise Up2Error(
            diag(
                "UP2-E1005",
                f"unsupported directive object {directive!r}",
                fix='only {"$lit": value} is supported today '
                "($map belongs to L2 structure assembly)",
                pointer=pointer,
            )
        )
    if len(active) != 1:
        raise Up2Error(
            diag(
                "UP2-E1005",
                f'{{"$lit": ...}} only works with a single-parameter action; {spec.name!r} has '
                f"{len(active)} parameters to fill",
                fix="write $lit at a specific parameter slot, or use a positional array",
                pointer=pointer,
                allowed=tuple(param.name for param in active),
            )
        )
    return {**preset, active[0].name: Lit(raw[directive])}


def _check_refs(params: Mapping[str, Param], *, products: tuple[str, ...], pointer: str) -> None:
    for ref in _iter_refs(params):
        if ref.root in _DEFERRED_ROOTS:
            raise Up2Error(
                diag(
                    "UP2-E1006",
                    f"{ref.raw} is unavailable in L1",
                    fix=_DEFERRED_FIX,
                    pointer=pointer,
                )
            )
        if ref.root in RESERVED_ROOTS:
            continue
        if ref.root in products:
            if ref.path and ref.path[0].startswith("_"):
                raise Up2Error(
                    diag(
                        "UP2-E1014",
                        f"{ref.raw} references the local key {ref.path[0]!r} across nodes",
                        fix="a `_` prefix marks a local value of this node; drop the underscore, "
                        "or use $fields.*",
                        pointer=pointer,
                    )
                )
            continue
        raise Up2Error(
            diag(
                "UP2-E1006",
                f"unknown reference root {ref.root!r}",
                fix="use a reserved root, or declare the earlier node product with --product",
                pointer=pointer,
                allowed=(*RESERVED_ROOTS, *products),
            )
        )


def _iter_refs(params: Mapping[str, Param]) -> tuple[Ref, ...]:
    found: list[Ref] = []

    def walk(node: Any) -> None:
        if isinstance(node, Ref):
            found.append(node)
        elif isinstance(node, Mapping):
            for item in node.values():
                walk(item)
        elif isinstance(node, (list, tuple)):
            for item in node:
                walk(item)

    walk(params)
    return tuple(found)
