"""Compile time: stage validation + parameter schema + precompile (design doc 01 §5, 02 §1-§4, §7).

Compile time **never touches the runtime**: it reads no file, performs no network call, and
evaluates nothing. Structural errors are eliminated here and the runtime only evaluates -- this is
where ``N3``, "a bad chain fails at compile time", lands.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Final

from . import registry
from .ast import (
    TRY_OPERATOR,
    CompiledField,
    CompiledStage,
    Lit,
    Param,
    Ref,
    Stage,
    loads,
    parse_stage,
)
from .errors import Up2Error, diag
from .limits import MAX_EACH_DEPTH, MAX_FIELDS_PER_MAP, MAX_STEPS_PER_FIELD
from .refs import LIT_DIRECTIVE, OBJ_ROOT, RESERVED_ROOTS, is_ref_text, parse_ref
from .values import type_name

logger = logging.getLogger("uniparser2")

_DIRECTIVE_PREFIX = "$"
NODE_OPERATOR: Final = "node"
"""The story-aware stage: a node call."""


def compile_field(
    source: Any,
    /,
    *,
    products: Iterable[str] = (),
    nodes: Iterable[str] = (),
    depth: int = 0,
    pointer: str = "",
    name: str = "",
) -> CompiledField:
    """Compile a stage array / field chain / JSON string into ``CompiledField``.

    An empty array is the **identity**: the chain answers the value it received, with no stage
    evaluated. ``[]`` is the only identity form; a string in chain position is not accepted.

    ``nodes`` is the story's node table (empty for a standalone chain): a ``["node", name]`` stage
    is checked against it, and a chain outside a story cannot call a node.

    ``depth`` counts the enclosing ``each`` field maps, ``pointer`` is the JSON Pointer prefix this
    chain sits at inside the chain being compiled, and ``name`` is the field-map key it was compiled
    as (the trace's ``field``, `06` §5.1).
    """
    if depth > MAX_EACH_DEPTH:
        raise Up2Error(
            diag(
                "UP2-E1012",
                f"`each` is nested {depth} levels deep, over MAX_EACH_DEPTH={MAX_EACH_DEPTH}",
                fix="split the iteration over several nodes, or flatten the inner list first",
                pointer=pointer,
            )
        )
    source_stages = (
        tuple(source.source)
        if isinstance(source, CompiledField)
        else loads(source, pointer=pointer)
    )
    if len(source_stages) > MAX_STEPS_PER_FIELD:
        raise Up2Error(
            diag(
                "UP2-E1012",
                f"field chain has {len(source_stages)} steps, over "
                f"MAX_STEPS_PER_FIELD={MAX_STEPS_PER_FIELD}",
                fix="split it into several field chains, or fold a piece of logic into a "
                "named operator/udf",
                pointer=pointer,
            )
        )
    declared = tuple(dict.fromkeys(products))
    node_names = tuple(dict.fromkeys(nodes))
    stages = tuple(
        compile_stage(
            stage,
            index=index,
            products=declared,
            nodes=node_names,
            depth=depth,
            pointer=pointer,
        )
        for index, stage in enumerate(source_stages)
    )
    _check_try_directives(source_stages, pointer=pointer)
    logger.debug("compiled field: steps=%d ops=%s", len(stages), [item.op_name for item in stages])
    return CompiledField(stages=stages, source=source_stages, name=name)


def _check_try_directives(source_stages: tuple[Stage, ...], *, pointer: str) -> None:
    """The guard directive's two rules: it guards the **next** stage, and only one may be pending.

    A directive as the last stage would guard nothing, and two in a row would leave the first
    guarding the second -- a directive, not a stage. Both are compile-time errors, so a chain that
    means something else never runs.
    """
    for index, stage in enumerate(source_stages):
        if stage.op != TRY_OPERATOR:
            continue
        if index + 1 >= len(source_stages):
            raise Up2Error(
                diag(
                    "UP2-E1005",
                    "a `try` directive must be followed by the stage it guards",
                    fix="move the `try` before the stage it protects, or drop it",
                    pointer=f"{pointer}/{index}",
                )
            )
        if source_stages[index + 1].op == TRY_OPERATOR:
            raise Up2Error(
                diag(
                    "UP2-E1005",
                    "two `try` directives in a row: the first would guard the second, not a stage",
                    fix="keep one directive and put the stage it guards right after it",
                    pointer=f"{pointer}/{index}",
                )
            )


def compile_stage(
    raw: Any,
    /,
    *,
    index: int = 0,
    products: Iterable[str] = (),
    nodes: Iterable[str] = (),
    depth: int = 0,
    pointer: str = "",
) -> CompiledStage:
    """Compile a single stage. ``pointer`` is the prefix of the chain this stage belongs to."""
    pointer = f"{pointer}/{index}"
    stage = raw if isinstance(raw, Stage) else parse_stage(raw, pointer=pointer)
    if stage.op == TRY_OPERATOR:
        return _compile_try_stage(stage, index=index, pointer=pointer)
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
        present=stage.length == instance.arity,
        preset=instance.action_params(action, action_text),
        pointer=f"{pointer}/{param_slot}",
        products=tuple(products),
        nodes=tuple(nodes),
        depth=depth,
    )
    _check_refs(params, products=tuple(products), pointer=f"{pointer}/{param_slot}")
    if instance.name == NODE_OPERATOR:
        _check_node_name(params, nodes=tuple(nodes), pointer=f"{pointer}/{param_slot}")
    payload = instance.precompile(action, params, pointer=f"{pointer}/{param_slot}")
    return CompiledStage(
        index=index,
        stage=stage,
        op_name=instance.name,
        action=action,
        params=params,
        payload=payload,
        json_pointer=pointer,
    )


def _check_node_name(params: Mapping[str, Param], *, nodes: tuple[str, ...], pointer: str) -> None:
    """A `node` stage names a node of the same story, checked at compile time."""
    raw = params["node"]
    name = raw.value if isinstance(raw, Lit) else raw
    if not isinstance(name, str) or name not in nodes:
        raise Up2Error(
            diag(
                "UP2-E1016",
                f"the node call names {name!r}, which is not a node of this story",
                fix="name a node of this story; a standalone chain has no nodes to call",
                pointer=pointer,
                allowed=nodes,
            )
        )


def _compile_try_stage(stage: Stage, /, *, index: int, pointer: str) -> CompiledStage:
    """The guard directive: a stage that carries a policy instead of doing work.

    It is compiled like a stage so the evaluator can see it in order, but it never runs: the
    evaluator reads the policy and applies it to the **next** stage's outcome. Its shape is exactly
    ``["try", policy]``; a third slot would be silently ignored, so it is rejected here.
    """
    if stage.length != 2:
        raise Up2Error(
            diag(
                "UP2-E1004",
                f"a `try` directive has 2 slots, got {stage.length}",
                fix='write ["try","skip"], ["try","break"] or ["try","raise"]',
                pointer=pointer,
            )
        )
    policy = stage.slot1
    if not isinstance(policy, str) or policy not in registry.TRY_POLICIES:
        raise Up2Error(
            diag(
                "UP2-E1005",
                f"a `try` directive needs a policy, got {policy!r}",
                fix="write the stage it guards right after the directive",
                pointer=f"{pointer}/1",
                allowed=registry.TRY_POLICIES,
            )
        )
    return CompiledStage(
        index=index,
        stage=stage,
        op_name=TRY_OPERATOR,
        action=policy,
        params={},
        payload=policy,
        json_pointer=pointer,
    )


def _slot(stage: Stage, index: int | None) -> Any:
    """Return one slot's raw text as declared by the operator; ``None`` means no such slot."""
    if index == 1:
        return stage.slot1
    if index == 2:
        return stage.slot2
    return None


def _check_arity(instance: registry.Op, stage: Stage, *, pointer: str) -> None:
    """The stage length is the operator's arity, or one shorter when the parameter is omitted."""
    if stage.length in (instance.arity, instance.arity - 1):
        return
    shape = ", ".join(f"slot{i + 2}={role}" for i, role in enumerate(instance.slot_roles))
    raise Up2Error(
        diag(
            "UP2-E1004",
            f"{stage.op} needs {instance.arity} slots, got {stage.length}",
            fix=f"this operator's slots are {shape}; drop the parameter slot when the action "
            "declares nothing required",
            pointer=pointer,
        )
    )


def _build_params(
    spec: registry.ActionSpec,
    raw: Any,
    *,
    present: bool,
    preset: Mapping[str, Param],
    pointer: str,
    products: tuple[str, ...] = (),
    nodes: tuple[str, ...] = (),
    depth: int = 0,
) -> dict[str, Param]:
    """Bind slot 3 by the action's declaration (02 §4).

    A parameter slot that is **absent** takes the defaults (``["py","strip"]``); a slot that is
    written binds the declared parameters **positionally**: one value for a one-parameter action,
    or one array for an action with several. An object is a data map, never a parameter list, so
    the only object accepted here is the ``$lit`` directive.
    """
    active = tuple(param for param in spec.params if param.name not in preset)
    if not present:
        return _fill_defaults(
            spec,
            active,
            {},
            preset=preset,
            pointer=pointer,
            products=products,
            nodes=nodes,
            depth=depth,
        )
    if not active:
        raise Up2Error(
            diag(
                "UP2-E1004",
                f"action {spec.name!r} takes no parameter, but {raw!r} was written in the slot",
                fix="drop the slot: the action has nothing left to configure",
                pointer=pointer,
            )
        )
    if (
        isinstance(raw, dict)
        and _directive_name(raw) is not None
        # A structural parameter (``each``'s field map) is not a value: an object there is the
        # map itself, so ``{"$lit": …}`` is a field named ``$lit``, not the escape directive.
        and all(
            param.kind not in (registry.Kind.FIELDS, registry.Kind.FIELDS_OR_CHAIN)
            for param in active
        )
    ):
        directive = _directive_name(raw) or ""
        return _directive_params(spec, active, raw, directive, preset=preset, pointer=pointer)
    if len(active) == 1:
        return _fill_defaults(
            spec,
            active,
            {active[0].name: raw},
            preset=preset,
            pointer=pointer,
            products=products,
            nodes=nodes,
            depth=depth,
        )
    if isinstance(raw, dict):
        raise Up2Error(
            diag(
                "UP2-E1005",
                f"action {spec.name!r} takes its {len(active)} parameters positionally, "
                "got an object",
                fix='write the parameters as one array, for example ["py","replace",[old,new]]',
                pointer=pointer,
            )
        )
    if isinstance(raw, (list, tuple)):
        return _positional_params(
            spec,
            active,
            raw,
            preset=preset,
            pointer=pointer,
            products=products,
            nodes=nodes,
            depth=depth,
        )
    # A scalar given to a multi-parameter action fills the first parameter; the rest take their
    # defaults (xpath's expression without a namespace map, for example).
    return _fill_defaults(
        spec,
        active,
        {active[0].name: raw},
        preset=preset,
        pointer=pointer,
        products=products,
        nodes=nodes,
        depth=depth,
    )


def _positional_params(
    spec: registry.ActionSpec,
    active: Sequence[registry.ParamSpec],
    raw: Any,
    *,
    preset: Mapping[str, Param],
    pointer: str,
    products: tuple[str, ...] = (),
    nodes: tuple[str, ...] = (),
    depth: int = 0,
) -> dict[str, Param]:
    required = sum(1 for param in active if param.required)
    if len(raw) > len(active):
        raise Up2Error(
            diag(
                "UP2-E1005",
                f"{len(raw)} parameters were given, the action accepts at most {len(active)}",
                fix=f"keep the first {len(active)}, in the declared order: {_param_order(active)}",
                pointer=pointer,
            )
        )
    if len(raw) < required:
        raise Up2Error(
            diag(
                "UP2-E1005",
                f"{len(raw)} parameters were given, the action needs at least {required}",
                fix=f"write them in the declared order: {_param_order(active)}",
                pointer=pointer,
                allowed=tuple(param.name for param in active),
            )
        )
    values = {param.name: value for param, value in zip(active, raw, strict=False)}
    return _fill_defaults(
        spec,
        active,
        values,
        preset=preset,
        pointer=pointer,
        products=products,
        nodes=nodes,
        depth=depth,
        keys={param.name: index for index, param in enumerate(active)},
    )


def _param_order(active: Sequence[registry.ParamSpec]) -> str:
    return ", ".join(
        f"{param.name} ({'required' if param.required else 'optional'})" for param in active
    )


def _fill_defaults(
    spec: registry.ActionSpec,
    active: Sequence[registry.ParamSpec],
    values: Mapping[str, Any],
    *,
    preset: Mapping[str, Param],
    pointer: str,
    products: tuple[str, ...] = (),
    nodes: tuple[str, ...] = (),
    depth: int = 0,
    keys: Mapping[str, int] | None = None,
) -> dict[str, Param]:
    """Merge the parameters the action slot provided, fill in defaults, and resolve by kind."""
    params: dict[str, Param] = dict(preset)
    for param in active:
        if param.name in values:
            suffix = str(keys[param.name]) if keys is not None else param.name
            params[param.name] = _resolve_param(
                param,
                values[param.name],
                pointer=f"{pointer}/{suffix}",
                products=products,
                nodes=nodes,
                depth=depth,
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


def _resolve_param(
    spec: registry.ParamSpec,
    raw: Any,
    *,
    pointer: str,
    products: tuple[str, ...] = (),
    nodes: tuple[str, ...] = (),
    depth: int = 0,
) -> Param:
    """Resolve by kind; containers are walked recursively (leaves take the same parameter kind).

    ``Kind.FIELDS`` is the exception: its containers are **chains**, so they are compiled here
    instead of being walked as values.
    """
    if spec.kind is registry.Kind.FIELDS:
        return _resolve_field_map(
            spec, raw, pointer=pointer, products=products, nodes=nodes, depth=depth
        )
    if spec.kind is registry.Kind.FIELDS_OR_CHAIN:
        return _resolve_field_map_or_chain(
            spec, raw, pointer=pointer, products=products, nodes=nodes, depth=depth
        )
    if spec.kind is registry.Kind.LITERAL:
        return Lit(raw)
    if isinstance(raw, list):
        return [
            _resolve_param(spec, item, pointer=pointer, products=products, nodes=nodes, depth=depth)
            for item in raw
        ]
    if isinstance(raw, dict):
        # A `ref` parameter must be a reference, so the escape does not reach it.
        if spec.kind is registry.Kind.REF_OR_LITERAL:
            quoted = _quoted_literal(raw, pointer=pointer)
            if quoted is not None:
                return quoted
        return {
            key: _resolve_param(
                spec, item, pointer=pointer, products=products, nodes=nodes, depth=depth
            )
            for key, item in raw.items()
        }
    return _resolve_leaf(spec, raw, pointer=pointer)


def _quoted_literal(raw: Mapping[str, Any], *, pointer: str) -> Param | None:
    """``{"$lit": …}`` at any depth: the escape is a directive wherever a value is read (02 §3.3).

    The rule is the slot's own (``02`` §4): an object with exactly one ``$``-prefixed key is a
    directive, not data. Applying it at every depth is what makes a literal starting with ``$``
    writable inside an array or an object — without it the same shape either leaked downstream as a
    dict or had its escaped text resolved as a reference a second time.
    """
    directive = _directive_name(raw)
    if directive is None:
        return None
    if directive != LIT_DIRECTIVE:
        raise Up2Error(
            diag(
                "UP2-E1005",
                f"unsupported directive object {directive!r}",
                fix='only {"$lit": value} is supported',
                pointer=pointer,
            )
        )
    return Lit(raw[directive])


def _resolve_field_map_or_chain(
    spec: registry.ParamSpec,
    raw: Any,
    *,
    pointer: str,
    products: tuple[str, ...],
    nodes: tuple[str, ...],
    depth: int,
) -> dict[str, CompiledField] | CompiledField:
    """``each``'s parameter: an object is a field map, an array is one chain (design D8)."""
    if isinstance(raw, Mapping):
        return _resolve_field_map(
            spec, raw, pointer=pointer, products=products, nodes=nodes, depth=depth
        )
    if isinstance(raw, (list, tuple)):
        return compile_field(
            raw,
            products=products,
            nodes=nodes,
            depth=depth + 1,
            pointer=pointer,
        )
    raise Up2Error(
        diag(
            "UP2-E1005",
            f"{spec.name} must be a field map or one chain, got {type_name(raw)}",
            fix='write {"title": [["py","strip"]]} for one dictionary per element, or '
            '[[["py","strip"]]] for one value per element',
            pointer=pointer,
        )
    )


def _resolve_field_map(
    spec: registry.ParamSpec,
    raw: Any,
    *,
    pointer: str,
    products: tuple[str, ...],
    nodes: tuple[str, ...],
    depth: int,
) -> dict[str, CompiledField]:
    """Compile a **field map** (``each``'s argument), named after the parameter for diagnostics."""
    return compile_field_map(
        spec.name, raw, products=products, nodes=nodes, depth=depth, pointer=pointer
    )


def compile_field_map(
    name: str,
    raw: Any,
    /,
    *,
    products: tuple[str, ...] = (),
    nodes: tuple[str, ...] = (),
    depth: int = 0,
    pointer: str = "",
) -> dict[str, CompiledField]:
    """Compile a **field map**: ``{field name: chain}``, every value a chain.

    The compiled chains are the payload the runtime only evaluates, so the shape is checked here:
    it must be non-empty, no larger than ``MAX_FIELDS_PER_MAP``, and every name addressable by a
    reference path. ``each``'s argument and a story node's field map are the same object shape,
    which is why this is public (the story layer compiles a node's field map with it).
    """
    if not isinstance(raw, Mapping):
        raise Up2Error(
            diag(
                "UP2-E1005",
                f"{name} must be an object of field name to chain, got {type_name(raw)}",
                fix='write {"title": [["py","strip"]]}',
                pointer=pointer,
            )
        )
    _check_field_map(raw, pointer=pointer)
    return {
        str(field): compile_field(
            item,
            products=products,
            nodes=nodes,
            depth=depth + 1,
            pointer=f"{pointer}/{field}",
            name=str(field),
        )
        for field, item in raw.items()
    }


def _check_field_map(fields: Mapping[Any, Any], *, pointer: str) -> None:
    """Reject a field map a chain cannot use: empty, oversized, or an unaddressable name."""
    if not fields:
        raise Up2Error(
            diag(
                "UP2-E1005",
                "the field map is empty, so every element would be an empty dictionary",
                fix='declare at least one field, e.g. {"title": [["py","strip"]]}',
                pointer=pointer,
            )
        )
    if len(fields) > MAX_FIELDS_PER_MAP:
        raise Up2Error(
            diag(
                "UP2-E1012",
                f"the field map declares {len(fields)} fields, over "
                f"MAX_FIELDS_PER_MAP={MAX_FIELDS_PER_MAP}",
                fix="drop the fields the chain does not read, or split the map over several nodes",
                pointer=pointer,
            )
        )
    for name in fields:
        text = str(name)
        if not text or "." in text:
            raise Up2Error(
                diag(
                    "UP2-E1005",
                    f"the field name {text!r} cannot be addressed by a reference path",
                    fix=f'rename {text!r} to a non-empty name without a dot, e.g. "_tmp"',
                    pointer=f"{pointer}/{text}",
                )
            )


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
                fix='only {"$lit": value} is supported; `each` takes a plain field map',
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
    if active[0].kind is registry.Kind.REF:
        # A parameter that must be a reference has no literal branch, so the escape cannot fill it.
        raise Up2Error(
            diag(
                "UP2-E1007",
                f'{{"$lit": ...}} cannot fill {active[0].name!r}: '
                "that parameter must be a reference",
                fix='write a reference such as "$globals.name" / "$locals._tmp"',
                pointer=pointer,
            )
        )
    return {**preset, active[0].name: Lit(raw[directive])}


def _check_refs(params: Mapping[str, Param], *, products: tuple[str, ...], pointer: str) -> None:
    """Every reference in a parameter tree (or in a whole-chain reference) must resolve.

    A chain and a parameter are checked against the same roots, because a leading `$` means the same
    thing in both positions (`03` §2).
    """
    for ref in _iter_refs(params):
        if ref.root == OBJ_ROOT and ref.path:
            raise Up2Error(
                diag(
                    "UP2-E1006",
                    f"{ref.raw} walks into `obj`, which names the whole value",
                    fix='read a field with ["py","getitem",K] after "$obj", or use $locals',
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
                        f"{ref.raw} references the local key {ref.path[0]!r} across steps",
                        fix="a `_` prefix marks a local value of this step; drop the underscore, "
                        "or read $locals.* in the step that wrote it",
                        pointer=pointer,
                    )
                )
            continue
        raise Up2Error(
            diag(
                "UP2-E1006",
                f"unknown reference root {ref.root!r}",
                fix=(
                    "use a reserved root, or declare an external product root with --product; "
                    'for text that starts with `$`, write {"$lit": "…"}'
                ),
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
