"""``json`` operator: JSON dot-path queries (design doc 02 §6.2).

**Slots** (see ``02`` §1): ``["json", jmespath path]`` — **only 2 slots**. It has exactly one
action (fetch a value along the path), so the chain omits the action slot and slot 2 is the path.

Expressions use ``jmespath`` (optional dependency): the expression is precompiled at **compile
time**, and a syntax error is reported on the spot as ``UP2-E1005``. The input may be JSON text
(parsed on demand, through the run-scoped materialization cache of `03` §6) or an already-parsed
value, which is walked as it is.

Naming: the ``04`` draft calls it ``json``; this design keeps that name and treats ``jmespath`` as
an alias.
"""

from __future__ import annotations

import importlib
import json
import sys
from collections.abc import Mapping
from typing import Any, ClassVar, Final

from ..core.ast import Lit, Param
from ..core.errors import Failed, Missing, Ok, Outcome, Up2Error, diag
from ..core.materialize import JSON
from ..core.registry import ActionSpec, Call, Kind, Op, ParamSpec, op
from ..core.values import is_json_value, preview, type_name

_GET: Final = "get"
"""The only action, **not written in the chain** (``["json", "path"]``).

The registry keeps a name so the parameter table and the conformance audit have something to use.
"""
_JMESPATH: Final = "jmespath"


def _import_jmespath() -> Any:
    """Import the optional dependency lazily (a dynamic import avoids missing-module reports)."""
    return importlib.import_module(_JMESPATH)


@op("json", aliases=("jmespath",))
class JsonQuery(Op):
    """Walk a jmespath path to fetch a subtree / list element / single value."""

    summary = "JSON dot-path query (jmespath)"
    requires = (_JMESPATH,)
    arity = 2
    slot_roles = ("jmespath path",)
    actions: ClassVar[Mapping[str, ActionSpec]] = {
        _GET: ActionSpec(
            _GET,
            "jmespath query (empty expression = the root)",
            (ParamSpec("expr", Kind.LITERAL, required=False, default=""),),
        )
    }

    def resolve_action(self, action_text: Any, *, pointer: str = "") -> str:
        del action_text, pointer  # single action: the chain omits the action slot
        return _GET

    def precompile(self, action: str, params: Mapping[str, Param], *, pointer: str = "") -> Any:
        del action
        expr = _literal_text(params, "expr", pointer=f"{pointer}/expr")
        module = _import_jmespath()
        try:
            return module.compile(expr)
        except Exception as exc:  # the jmespath syntax-error type is not stable
            raise Up2Error(
                diag(
                    "UP2-E1005",
                    f"invalid jmespath expression: {exc}",
                    fix=(
                        "fix the path (e.g. data.list[*].url, data.html, "
                        "or an empty string for the root)"
                    ),
                    pointer=f"{pointer}/expr",
                )
            ) from exc

    def evaluate(self, call: Call) -> Outcome:
        data = call.value
        if isinstance(data, str):
            try:
                data = _parsed(call, data)
            except ValueError as exc:
                return Failed(
                    code="UP2-E2005",
                    reason=f"json input is not valid JSON: {exc}",
                    fix=(
                        "confirm the upstream value really is JSON text, or extract a substring "
                        "with py.getitem first"
                    ),
                )
        if not is_json_value(data):
            return Failed(
                code="UP2-E2002",
                reason=f"json needs a JSON value, got {type_name(data)} ({preview(data, 60)})",
                fix="pass JSON text or an already-parsed value from upstream",
            )
        try:
            found = call.payload.search(data)
        except Exception as exc:
            return Failed(code="UP2-E2005", reason=f"jmespath query failed: {exc}")
        if found is None:
            return Missing(reason="the jmespath expression matched nothing")
        return Ok(found)


def _parsed(call: Call, text: str) -> Any:
    """The JSON tree for ``text``: one parse per run, through the materializer (`03` §6).

    Only a ``str`` input is materialized; a value that is already a JSON tree is walked as it is.
    The tree is only read (``jmespath.search``), so the cached artifact is never mutated.
    """

    def build(source: str) -> tuple[Any, int]:
        tree = json.loads(source)
        return tree, tree_bytes(tree)

    return call.cache.get(JSON, text, build)


def tree_bytes(value: Any) -> int:
    """The materialized size of one JSON tree, in bytes (`03` §6).

    Measured, a JSON tree costs ~2.2-2.7x its text, so the text alone would understate the bound.
    The walk counts container headers plus the payload of the strings and adds no copy of the tree,
    so it cannot amplify the memory it is measuring (``MAX_TEXT_BYTES`` bounds the source text).
    """
    total = 0
    pending = [value]
    while pending:
        item = pending.pop()
        total += sys.getsizeof(item)
        if isinstance(item, (list, tuple)):
            pending.extend(item)
        elif isinstance(item, dict):
            pending.extend(item.keys())
            pending.extend(item.values())
    return total


def _literal_text(params: Mapping[str, Param], name: str, *, pointer: str = "") -> str:
    value = params[name]
    text = value.value if isinstance(value, Lit) else value
    if not isinstance(text, str):
        raise Up2Error(
            diag(
                "UP2-E1005",
                f"parameter {name!r} must be a string, got {type_name(text)}",
                fix="write the path as a jmespath expression string",
                pointer=pointer or f"/1/{name}",
            )
        )
    return text
