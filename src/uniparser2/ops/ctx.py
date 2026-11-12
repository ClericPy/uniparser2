"""``ctx`` operator: scope reads and writes (design docs 02 §6.8, 03 §8).

**The write surface is limited to ``locals`` and ``public``**: writing ``globals`` or a product root
raises ``UP2-E1015``. Rationale: if ``globals`` could be modified, the same value would evaluate
differently in different fields and purity (``N1``) would break; if a product value could be
modified, downstream references would read intermediate states. ``public`` is writable because it is
the run's own notes, not chain data (``chain-iteration``): a value written there is runtime state,
never part of the chain's identity.

Paths are written as **bare path literals** (``locals._tmp`` / ``globals.base_url``), with no ``$``
and no ``ctx.`` prefix — because the target that ``set``/``del`` operates on does not exist yet and
cannot be handed to the reference evaluator for reading. This unifies the two spellings mixed in
the `04` draft (``ctx.locals._raw`` / ``"locals.a.b"``).

**The collection actions name their shape** (`ctx-dict-list-and-py-table`): ``dict`` takes an object
of name → path and yields an object, ``list`` takes an array of paths and yields an array. One
polymorphic ``map`` used to answer two different types depending on its parameter's shape; the
action name now says what comes out.
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
_DICT: Final = "dict"
_LIST: Final = "list"
_WRITABLE_PREFIXES: Final = ("locals", "public")
_READABLE_ROOTS: Final = ("globals", "locals", "public", "obj")


@op("ctx")
class Ctx(Op):
    """Scope reads and writes: ``globals`` is read-only; ``locals`` and ``public`` are writable."""

    summary = "Scope reads and writes (get / set / del / dict / list)"
    actions: ClassVar[Mapping[str, ActionSpec]] = {
        _GET: ActionSpec(_GET, "read a scope path", (ParamSpec("path", Kind.LITERAL),)),
        _SET: ActionSpec(
            _SET,
            "write the upstream value into locals or public",
            (ParamSpec("path", Kind.LITERAL),),
        ),
        _DEL: ActionSpec(
            _DEL, "delete a path in locals or public", (ParamSpec("path", Kind.LITERAL),)
        ),
        _DICT: ActionSpec(
            _DICT,
            "collect several paths into an object (name → path)",
            (ParamSpec("refs", Kind.LITERAL),),
        ),
        _LIST: ActionSpec(
            _LIST,
            "collect several paths into a list (an array of paths)",
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
                        fix=_write_fix(path),
                        pointer=f"{pointer}/path",
                        allowed=_WRITABLE_PREFIXES,
                    )
                )
            return path
        if action == _GET:
            path = _literal_text(params, "path")
            _check_readable(path, action=action, pointer=f"{pointer}/path")
            return path
        raw = _unwrap(params["refs"])
        paths = _collect_paths(raw, action=action, pointer=f"{pointer}/refs")
        # In the object form the paths live in the values, and iterating a dict yields keys, so
        # the two forms must be handled separately.
        for path in paths.values() if isinstance(paths, dict) else paths:
            _check_readable(path, action=action, pointer=f"{pointer}/refs")
        return paths

    def evaluate(self, call: Call) -> Outcome:
        if call.action == _GET:
            return _read(call, call.payload)
        if call.action == _SET:
            call.scope.write_text(call.payload, call.value)
            return Ok(call.value)
        if call.action == _DEL:
            call.scope.delete_text(call.payload)
            return Ok(call.value)
        return _build(call)


def _read(call: Call, path: str) -> Outcome:
    """Read a ctx path: ``obj`` is the value the stage received, every other root is a scope."""
    if path == "obj":
        return Ok(call.value)
    return call.scope.read_text(path)


def _build(call: Call) -> Outcome:
    """``dict`` / ``list``: collect the values of several paths into the payload's shape."""
    spec = call.payload
    if isinstance(spec, list):
        values: list[Any] = []
        for path in spec:
            outcome = _read(call, path)
            if not isinstance(outcome, Ok):
                return outcome
            values.append(outcome.value)
        return Ok(values)
    mapped: dict[str, Any] = {}
    for name, path in spec.items():
        outcome = _read(call, path)
        if not isinstance(outcome, Ok):
            return outcome
        mapped[name] = outcome.value
    return Ok(mapped)


def _collect_paths(raw: Any, *, action: str, pointer: str) -> list[str] | dict[str, str]:
    """The path set of a collection action: ``list`` takes an array, ``dict`` a name → path map."""
    if action == _LIST:
        if not isinstance(raw, list):
            raise Up2Error(
                diag(
                    "UP2-E1005",
                    f"ctx.list needs an array of paths, got {type(raw).__name__}",
                    fix='write ["locals.a","locals.b"]',
                    pointer=pointer,
                )
            )
        return [_require_text(item, pointer=pointer) for item in raw]
    if not isinstance(raw, dict):
        raise Up2Error(
            diag(
                "UP2-E1005",
                f"ctx.dict needs a name → path object, got {type(raw).__name__}",
                fix='write {"title":"locals._t"}',
                pointer=pointer,
            )
        )
    return {str(key): _require_text(item, pointer=f"{pointer}/{key}") for key, item in raw.items()}


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


def _read_fix(path: str) -> str:
    """A leading ``$`` is the mistake worth naming; otherwise the root is the problem."""
    if path.startswith("$"):
        return f'ctx takes a bare path, without `$`: write "{path[1:]}"'
    return f"use {' / '.join(_READABLE_ROOTS)} — written bare, e.g. locals.k"


def _write_fix(path: str) -> str:
    """Same rule on the write side: name a ``$`` before the write surface."""
    if path.startswith("$"):
        return f'ctx takes a bare path, without `$`: write "{path[1:]}"'
    return (
        "the write surface is limited to locals.* and public.* "
        "(globals and product values are read-only)"
    )


def _check_readable(path: str, *, action: str, pointer: str = "") -> None:
    root = path.split(".", 1)[0]
    if root == "obj" and path != "obj":
        raise Up2Error(
            diag(
                "UP2-E1005",
                f"ctx.{action} path {path!r} walks into obj",
                fix='obj names the whole value: read ["ctx","get","obj"], then a field with '
                '["py","getitem",…]',
                pointer=pointer,
            )
        )
    if root not in _READABLE_ROOTS:
        raise Up2Error(
            diag(
                "UP2-E1005",
                f"the root {root!r} of ctx.{action} is not readable",
                fix=_read_fix(path),
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
