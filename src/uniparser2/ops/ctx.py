"""``ctx`` operator: scope reads and writes (design docs 02 §6.8, 03 §8).

**The write surface is hard-limited to ``locals``/``fields``**: writing ``globals`` or a node's
output raises ``UP2-E1015``. Rationale: if ``globals`` could be modified, the same value would
evaluate differently in different fields and purity (``N1``) would break; if a node's output could
be modified, downstream references would read intermediate states.

Paths are written as **bare path literals** (``locals._tmp`` / ``globals.base_url``), with no ``$``
and no ``ctx.`` prefix — because the target that ``set``/``del`` operates on does not exist yet and
cannot be handed to the reference evaluator for reading. This unifies the two spellings mixed in
the `04` draft (``ctx.locals._raw`` / ``"locals.a.b"``).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar, Final

from ..core.ast import Lit, Param
from ..core.errors import Ok, Outcome, Up2Error, diag
from ..core.registry import ActionSpec, Call, Kind, Op, ParamSpec, op

_GET: Final = "get"
_SET: Final = "set"
_DEL: Final = "del"
_MAP: Final = "map"
_WRITABLE_PREFIXES: Final = ("locals", "fields")
_READABLE_ROOTS: Final = ("globals", "locals", "fields")


@op("ctx")
class Ctx(Op):
    """Scope reads and writes: ``globals`` is read-only, ``locals``/``fields`` are writable."""

    summary = "Scope reads and writes (get / set / del / map)"
    actions: ClassVar[Mapping[str, ActionSpec]] = {
        _GET: ActionSpec(_GET, "read a scope path", (ParamSpec("path", Kind.LITERAL),)),
        _SET: ActionSpec(
            _SET, "write the upstream value into locals", (ParamSpec("path", Kind.LITERAL),)
        ),
        _DEL: ActionSpec(_DEL, "delete a path in locals", (ParamSpec("path", Kind.LITERAL),)),
        _MAP: ActionSpec(
            _MAP,
            "collect several values into a list or a dict",
            (ParamSpec("refs", Kind.LITERAL),),
        ),
    }

    def precompile(self, action: str, params: Mapping[str, Param], *, pointer: str = "") -> Any:
        if action in (_SET, _DEL):
            path = _literal_text(params, "path")
            if not path.startswith(_WRITABLE_PREFIXES):
                raise Up2Error(
                    diag(
                        "UP2-E1015",
                        f"ctx.{action} cannot write {path!r}",
                        fix=(
                            "the write surface is limited to locals.* / fields.* "
                            "(globals and node output are read-only)"
                        ),
                        pointer=f"{pointer}/path",
                        allowed=_WRITABLE_PREFIXES,
                    )
                )
            return path
        if action == _GET:
            path = _literal_text(params, "path")
            _check_readable(path, action=action, pointer=f"{pointer}/path")
            return path
        paths = _collect_paths(_unwrap(params["refs"]), pointer=f"{pointer}/refs")
        # In the object form the paths live in the values, and iterating a dict yields keys, so
        # the two forms must be handled separately.
        for path in paths.values() if isinstance(paths, dict) else paths:
            _check_readable(path, action=action, pointer=f"{pointer}/refs")
        return paths

    def evaluate(self, call: Call) -> Outcome:
        if call.action == _GET:
            return call.scope.read_text(call.payload)
        if call.action == _SET:
            call.scope.write_text(call.payload, call.value)
            return Ok(call.value)
        if call.action == _DEL:
            call.scope.delete_text(call.payload)
            return Ok(call.value)
        return _build_map(call)


def _build_map(call: Call) -> Outcome:
    """``map``: collect the values of several paths into a list or a dict.

    The array form yields a list and the object form a dict.
    """
    spec = call.payload
    if isinstance(spec, list):
        values: list[Any] = []
        for path in spec:
            outcome = call.scope.read_text(path)
            if not isinstance(outcome, Ok):
                return outcome
            values.append(outcome.value)
        return Ok(values)
    mapped: dict[str, Any] = {}
    for name, path in spec.items():
        outcome = call.scope.read_text(path)
        if not isinstance(outcome, Ok):
            return outcome
        mapped[name] = outcome.value
    return Ok(mapped)


def _collect_paths(raw: Any, *, pointer: str) -> list[str] | dict[str, str]:
    """The path set for ``map``: array → list, object → dict (the values must be path text)."""
    if isinstance(raw, list):
        return [_require_text(item, pointer=pointer) for item in raw]
    if isinstance(raw, dict):
        return {
            str(key): _require_text(item, pointer=f"{pointer}/{key}") for key, item in raw.items()
        }
    raise Up2Error(
        diag(
            "UP2-E1005",
            f"ctx.map needs an array of paths or a name→path object, got {type(raw).__name__}",
            fix='write ["locals.a","locals.b"] or {"title":"locals._t"}',
            pointer=pointer,
        )
    )


def _require_text(raw: Any, *, pointer: str) -> str:
    if not isinstance(raw, str) or not raw:
        raise Up2Error(
            diag(
                "UP2-E1005",
                f"a path must be a string, got {type(raw).__name__}",
                fix='write path text such as "locals._tmp" (without $)',
                pointer=pointer,
            )
        )
    return raw


def _check_readable(path: str, *, action: str, pointer: str = "") -> None:
    root = path.split(".", 1)[0]
    if root not in _READABLE_ROOTS:
        raise Up2Error(
            diag(
                "UP2-E1005",
                f"the root {root!r} of ctx.{action} is not readable",
                fix="use globals / locals / fields",
                pointer=pointer,
                allowed=_READABLE_ROOTS,
            )
        )


def _unwrap(node: Param) -> Any:
    """Extract the raw value inside a ``Lit``.

    Path parameters are LITERAL, so at compile time they arrive wrapped in a ``Lit``.
    """
    return node.value if isinstance(node, Lit) else node


def _literal_text(params: Mapping[str, Param], name: str) -> str:
    value = params[name]
    text = value.value if isinstance(value, Lit) else value
    if not isinstance(text, str) or not text:
        raise Up2Error(
            diag(
                "UP2-E1005",
                f"parameter {name!r} must be a non-empty string path",
                fix='write "locals._tmp"',
                pointer=f"/2/{name}",
            )
        )
    return text
