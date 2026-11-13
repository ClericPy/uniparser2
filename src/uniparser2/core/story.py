"""The story layer: a story is a map of callable nodes, run synchronously (design doc 03 §2-§5).

A **story** is ``{"globals": {...}, "nodes": {...}}``. A node body is a **chain** (an array;
``[]`` is identity) or a **field map** (an object). A chain calls another node with
``["node", name]``, and a chain ends with ``["type", name]`` when the product has a registered
shape.

Composition is a call, not a route: there is no ``entry``, ``collect``, ``next`` or effect. ``run``
compiles the story, executes the node it names (the first node when it names none) and returns that
node's product. A failure raises ``Up2Error`` carrying the diagnostic and the node's JSON Pointer;
the run's exit passes through the single exit (``pack``).

The kernel performs no IO and is synchronous: host code enters only through ``udf`` (``fetch``
is the conventional downloader), and a udf that answers an awaitable is rejected.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping, Sequence
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Any, Final

from .ast import CompiledField, CompiledStage
from .compile import compile_field, compile_field_map
from .errors import Failed, Up2Error, diag
from .evaluator import eval_field, eval_field_map
from .export import pack
from .limits import MAX_STORY_NODES
from .refs import RESERVED_ROOTS, Scope
from .trace import Trace
from .types import TypeConstructor, all_types
from .udfs import UdfFn, all_udfs, use_udfs
from .values import type_name

logger = logging.getLogger("uniparser2")

_BUNDLE_KEYS: Final = frozenset({"globals", "nodes"})
_FORBIDDEN_NODE_CHARS: Final = (".", "/", "~")
_NODE_OPERATOR: Final = "node"
_UDF_OPERATOR: Final = "udf"
_EACH_OPERATOR: Final = "each"
_UNVISITED: Final = 0
"""The node-call graph node a walk has not reached yet."""
_ON_PATH: Final = 1
"""The graph node the walk is standing on: entering it again closes a cycle."""
_WALKED: Final = 2
"""The graph node whose whole subtree the walk has already left."""


@dataclass(frozen=True, slots=True)
class CompiledNode:
    """One compiled node: its name, its body (a chain or a field map), and its pointer."""

    name: str
    body: CompiledField | Mapping[str, CompiledField]
    pointer: str


@dataclass(frozen=True, slots=True)
class CompiledStory:
    """A compiled bundle: the constants, the nodes and the udf names the story uses."""

    globals: Mapping[str, Any]
    nodes: Mapping[str, CompiledNode]
    udf_names: frozenset[str]
    source: Any

    def udf_names_for(self, node: str) -> frozenset[str]:
        """The udf names reachable from ``node``; a run needs only these."""
        return frozenset(_reachable_udfs(self, node))


def compile_story(
    bundle: Any,
    /,
    *,
    udfs: Mapping[str, UdfFn] | None = None,
    pointer: str = "",
) -> CompiledStory:
    """Compile a story bundle; a bad bundle fails here, never halfway through a run (`N3`).

    ``udfs`` is the table a run will use (its overlay included), so a `udf` signature can be checked
    at compile time when the function is known. A plain lint passes none and sees the process-wide
    table.
    """
    if not isinstance(bundle, Mapping):
        raise _bad(f"a story must be a JSON object, got {type_name(bundle)}", pointer=pointer)
    unknown = sorted(str(key) for key in bundle if key not in _BUNDLE_KEYS)
    if unknown:
        raise _bad(
            f"unknown bundle keys: {', '.join(unknown)}",
            pointer=pointer,
            fix="a story carries `globals` (optional) and `nodes`; every node is callable",
            allowed=tuple(sorted(_BUNDLE_KEYS)),
        )
    globals_map = _globals(bundle.get("globals"), pointer=f"{pointer}/globals")
    raw_nodes = bundle.get("nodes")
    if not isinstance(raw_nodes, Mapping) or not raw_nodes:
        raise _bad(
            f"`nodes` must be a non-empty object, got {type_name(raw_nodes)}",
            pointer=f"{pointer}/nodes",
            fix='declare at least one node: {"nodes": {"parse": [["py","strip"]]}}',
        )
    if len(raw_nodes) > MAX_STORY_NODES:
        raise Up2Error(
            diag(
                "UP2-E1012",
                f"the story declares {len(raw_nodes)} nodes, over "
                f"MAX_STORY_NODES={MAX_STORY_NODES}",
                fix="split the story, or fold several nodes into one field map",
                pointer=f"{pointer}/nodes",
            )
        )
    names = _node_names(raw_nodes, pointer=f"{pointer}/nodes")
    context = use_udfs(udfs) if udfs is not None else nullcontext()
    with context:
        nodes = {
            name: _compile_node(
                raw,
                name=name,
                names=names,
                pointer=f"{pointer}/nodes/{name}",
            )
            for name, raw in raw_nodes.items()
        }
    story = CompiledStory(
        globals=globals_map,
        nodes=nodes,
        udf_names=frozenset(_used_udfs(nodes.values())),
        source=bundle,
    )
    _lint_node_graph(story)
    logger.debug("compiled story: nodes=%s", ", ".join(story.nodes))
    return story


def run(
    bundle: Any,
    node: str | None = None,
    input: Any = None,  # noqa: A002 - the facade's public name
    *,
    globals: Mapping[str, Any] | None = None,  # noqa: A002 - the story's own key
    udfs: Mapping[str, UdfFn] | None = None,
    types: Mapping[str, TypeConstructor] | Sequence[TypeConstructor] | None = None,
    trace: Trace | None = None,
) -> Any:
    """Compile the story, run one node synchronously, and return its product.

    ``node`` defaults to the first node in the document. ``globals`` merges over the story's
    constants for this run; ``udfs`` merges over the process-wide udf table and ``types`` over the
    process-wide type registry, both for this run only. A udf name the chosen node uses (directly or
    through a node call) but the effective table lacks is ``UP2-E1010``, raised before evaluation.
    The product passes through ``pack``; a non-JSON exit is ``UP2-E2003`` at the entry node.

    ``types`` is a name → constructor mapping, or a sequence of callables whose ``__name__`` is the
    name. The merged table reaches a `type` stage through the scope, so two runs in one process may
    resolve one name differently without touching the process-wide registry.
    """
    merged_udfs = {**all_udfs(), **(udfs or {})}
    merged_types = {**all_types(), **_type_overlay(types)}
    story = compile_story(bundle, udfs=merged_udfs)
    entry = _entry_name(story, node)
    missing = sorted(story.udf_names_for(entry) - merged_udfs.keys())
    if missing:
        raise Up2Error(
            diag(
                "UP2-E1010",
                f"the story uses udf(s) the run did not register: {', '.join(missing)}",
                fix="pass them as run(..., udfs={...}) or register_udf(name, function)",
                pointer=f"{story.nodes[entry].pointer}",
                allowed=tuple(sorted(merged_udfs)),
            )
        )
    effective_globals = {**story.globals, **(globals or {})}
    scope = Scope(
        globals=effective_globals,
        step_input=input,
        udfs=merged_udfs,
        types=merged_types,
    )
    runner = _NodeRunner(story, scope, trace)
    product = runner.call(entry, input)
    packed = pack(product)
    if isinstance(packed, Failed):
        raise Up2Error(
            diag(
                packed.code,
                packed.reason,
                fix=packed.fix,
                pointer=story.nodes[entry].pointer,
            )
        )
    return product


def _type_overlay(
    types: Mapping[str, TypeConstructor] | Sequence[TypeConstructor] | None,
) -> dict[str, TypeConstructor]:
    """A run's own type table: a name → constructor mapping, or callables named by ``__name__``."""
    if types is None:
        return {}
    if isinstance(types, Mapping):
        return dict(types)
    return {item.__name__: item for item in types}


def _entry_name(story: CompiledStory, node: str | None) -> str:
    """The node the run starts at: the named one, or the first node in the document."""
    if node is None:
        return next(iter(story.nodes))
    if node not in story.nodes:
        raise Up2Error(
            diag(
                "UP2-E1016",
                f"the story has no node named {node!r}",
                fix="name a node of this story, or omit the name to run the first node",
                pointer="",
                allowed=tuple(story.nodes),
            )
        )
    return node


class _NodeRunner:
    """Execute nodes against one run's scope, restoring the caller's ``$in`` after every call."""

    __slots__ = ("_scope", "_story", "_trace")

    def __init__(self, story: CompiledStory, scope: Scope, trace: Trace | None) -> None:
        self._story = story
        self._scope = scope
        self._trace = trace

    def call(self, name: str, value: Any, scope: Scope | None = None) -> Any:
        node = self._story.nodes[name]
        active = scope if scope is not None else self._scope
        previous = active.step_input
        active.step_input = value
        if self._trace is not None:
            self._trace.enter(name)
        try:
            outcome = (
                eval_field_map(
                    node.body,
                    value,
                    scope=active,
                    run_chain=self._chain_runner,
                )
                if isinstance(node.body, Mapping)
                else eval_field(
                    node.body,
                    value,
                    scope=active,
                    trace=self._trace,
                    node_runner=self.call,
                )
            )
            if isinstance(outcome, Failed):
                raise Up2Error(
                    diag(outcome.code, outcome.reason, fix=outcome.fix, pointer=node.pointer)
                )
            return outcome.value
        finally:
            active.step_input = previous
            if self._trace is not None:
                self._trace.leave()

    def _chain_runner(self, chain: CompiledField, value: Any, scope: Scope) -> Any:
        return eval_field(
            chain,
            value,
            scope=scope,
            trace=self._trace,
            node_runner=self.call,
        )


# ---------------------------------------------------------------- compile time


def _compile_node(
    raw: Any,
    *,
    name: str,
    names: tuple[str, ...],
    pointer: str,
) -> CompiledNode:
    if isinstance(raw, Mapping):
        body: CompiledField | Mapping[str, CompiledField] = compile_field_map(
            name, raw, nodes=names, pointer=pointer
        )
    elif isinstance(raw, (list, tuple)):
        body = compile_field(raw, nodes=names, pointer=pointer)
    else:
        raise _bad(
            f"node {name!r} must be a chain (array) or a field map (object), got {type_name(raw)}",
            pointer=pointer,
            fix="write an array of stages, [] for identity, or an object of field name to chain",
        )
    return CompiledNode(name=name, body=body, pointer=pointer)


def _node_names(raw_nodes: Mapping[Any, Any], *, pointer: str) -> tuple[str, ...]:
    """Every node name: non-empty, unique by key, addressable, and not a reserved root."""
    names: list[str] = []
    for name in raw_nodes:
        if not isinstance(name, str) or not name:
            raise Up2Error(
                diag(
                    "UP2-E1009",
                    f"every node needs a non-empty name, got {name!r}",
                    fix='name the node, e.g. "parse"',
                    pointer=pointer,
                )
            )
        if name in RESERVED_ROOTS:
            raise Up2Error(
                diag(
                    "UP2-E1009",
                    f"the node name {name!r} is a reserved reference root",
                    fix="rename the node; the reserved roots are used by references",
                    pointer=f"{pointer}/{name}",
                    allowed=RESERVED_ROOTS,
                )
            )
        bad = next((char for char in _FORBIDDEN_NODE_CHARS if char in name), None)
        if bad is not None:
            raise Up2Error(
                diag(
                    "UP2-E1009",
                    f"the node name {name!r} contains {bad!r}, which a JSON Pointer cannot name",
                    fix="use letters, digits, `_` or `-`",
                    pointer=f"{pointer}/{name}",
                )
            )
        names.append(name)
    return tuple(names)


def _used_udfs(nodes: Iterable[CompiledNode]) -> set[str]:
    """Every udf name the story's stages mention (nested `each` sub-chains included)."""
    found: set[str] = set()
    for node in nodes:
        for stage in _stages_of(node.body):
            if stage.op_name == _UDF_OPERATOR:
                found.add(stage.action)
    return found


def _reachable_udfs(story: CompiledStory, entry: str) -> set[str]:
    """The udf names reachable from ``entry``; a run does not require a sibling node's udfs."""
    seen: set[str] = set()
    stack = [entry]
    found: set[str] = set()
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        node = story.nodes[name]
        found.update(_used_udfs([node]))
        stack.extend(target for target, _stage in _node_edges(node.body))
    return found


def _stages_of(body: CompiledField | Mapping[str, CompiledField]) -> Iterable[CompiledStage]:
    if isinstance(body, Mapping):
        for chain in body.values():
            yield from chain.stages
            for stage in chain.stages:
                yield from _nested_stages(stage)
        return
    yield from body.stages
    for stage in body.stages:
        yield from _nested_stages(stage)


def _nested_stages(stage: CompiledStage) -> Iterable[CompiledStage]:
    """The stages inside an `each` payload, recursively."""
    if stage.op_name != _EACH_OPERATOR:
        return
    payload = stage.payload
    if isinstance(payload, Mapping):
        for chain in payload.values():
            yield from chain.stages
            for nested in chain.stages:
                yield from _nested_stages(nested)
    elif isinstance(payload, CompiledField):
        yield from payload.stages
        for nested in payload.stages:
            yield from _nested_stages(nested)


# ---------------------------------------------------------------- the node-call graph


def _lint_node_graph(story: CompiledStory) -> None:
    """Reject a node-call graph that closes a cycle (`UP2-E1017`)."""
    edges = {
        name: [(target, stage) for target, stage in _node_edges(node.body)]
        for name, node in story.nodes.items()
    }
    colours = dict.fromkeys(story.nodes, _UNVISITED)
    for name in story.nodes:
        closed = _walk(name, edges, colours, path=[])
        if closed is not None:
            raise _cycle(closed, story)


def _node_edges(body: CompiledField | Mapping[str, CompiledField]) -> Iterable[tuple[str, Any]]:
    for stage in _stages_of(body):
        if stage.op_name == _NODE_OPERATOR:
            yield stage.payload, stage


def _walk(
    name: str,
    edges: Mapping[str, list[tuple[str, CompiledStage]]],
    colours: dict[str, int],
    *,
    path: list[str],
) -> list[str] | None:
    colours[name] = _ON_PATH
    path.append(name)
    try:
        for target, _stage in edges[name]:
            if colours[target] == _ON_PATH:
                return [*path[path.index(target) :], target]
            if colours[target] == _UNVISITED:
                closed = _walk(target, edges, colours, path=path)
                if closed is not None:
                    return closed
        return None
    finally:
        path.pop()
        colours[name] = _WALKED


def _cycle(closed: list[str], story: CompiledStory) -> Up2Error:
    travel = " -> ".join(closed)
    source = story.nodes[closed[-2]] if len(closed) > 1 else story.nodes[closed[0]]
    pointer = source.pointer
    for target, stage in _node_edges(source.body):
        if target == closed[0]:
            pointer = stage.pointer
            break
    return Up2Error(
        diag(
            "UP2-E1017",
            f"the node calls close a cycle: {travel}",
            fix="break the cycle by inlining one node, or by running two calls from the host",
            pointer=pointer,
        )
    )


# ---------------------------------------------------------------- small helpers


def _globals(raw: Any, *, pointer: str) -> Mapping[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise _bad(f"`globals` must be an object, got {type_name(raw)}", pointer=pointer)
    return dict(raw)


def _bad(message: str, *, pointer: str, fix: str = "", allowed: tuple[str, ...] = ()) -> Up2Error:
    return Up2Error(diag("UP2-E1005", message, fix=fix, pointer=pointer, allowed=allowed))


__all__ = [
    "CompiledNode",
    "CompiledStory",
    "compile_story",
    "run",
]
