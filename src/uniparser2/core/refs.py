"""Reference syntax and scope (design doc 02 §3, 03 §8).

One rule covers everything: **a leading ``$`` means a reference; a ``$``-prefixed literal is
written ``{"$lit": ...}``; everything else is a literal.**
(Whether a string counts as a reference is decided by the parameter kind, see
``core.registry.Kind``.)

Scope (L1):
- ``globals``: the chain-level read-only environment.
- ``locals`` / ``fields``: the scope of the current field (writable). L1 has no nodes, so both
  name the same namespace; L2 merges node products into ``fields``.
- ``<node key>``: the product of an earlier node, injected by the caller as ``products``
  (read-only).

Scopes form a lineage: ``Scope.child()`` gives one iteration of ``each`` its own ``locals``, and a
read falls back outward **by name** -- the innermost scope holding the first segment of a path
resolves the whole path, so a name the current scope wrote never resolves in an outer scope. There
is no iteration variable to name — the current element is the input value of the sub-chain (the
``item`` root is gone).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from .ast import Ref
from .errors import Failed, Missing, Ok, Outcome, Up2Error, diag
from .values import MISSING, is_json_value, type_name

REF_PREFIX: Final = "$"
LIT_DIRECTIVE: Final = "$lit"
RESERVED_ROOTS: Final = ("globals", "locals", "fields", "in")
WRITABLE_ROOTS: Final = ("locals", "fields")
INPUT_ROOT: Final = "in"
"""The root naming **this step's own input** (``$in.url``, design doc 03 §2.1).

A story step's input is the value the step was handed (the previous step's product, a host answer,
or the run's own input for the first step), and it has no ``locals`` round-trip: ``$in`` names it.
"""
# In L1, $fields and $locals name the scope of the current field; L2 splits them (the node's
# product versus the scratch area) and adds the per-element scope that `each` already needs.
_LOCAL_ALIASES: Final = ("locals", "fields")
CTX_PARTITIONS: Final = ("locals", "globals")
"""The two partitions the scope exposes (``ctx.locals`` / ``ctx.globals``, design doc 01 Q40).

``code`` operators project the scope into the sandbox through it, and ``udf`` builds a same-named
object for the host function -- both sides share this single definition, which guarantees that
"the same ``ctx``" looks alike in in-chain code and in host functions.
"""


def is_ref_text(text: object) -> bool:
    """Whether the text looks like a reference (kind detection only; not a validity claim)."""
    return isinstance(text, str) and text.startswith(REF_PREFIX)


def parse_ref(text: str, /, *, pointer: str = "") -> Ref:
    """Parse the reference shape; an empty root or an empty segment is ``UP2-E1006``."""
    body = text[len(REF_PREFIX) :]
    if not body:
        raise Up2Error(
            diag(
                "UP2-E1006",
                "the reference is only a `$`, with no root",
                fix="write $globals.name / $locals._tmp / $<node key>.field",
                pointer=pointer,
            )
        )
    parts = body.split(".")
    if any(part == "" for part in parts):
        raise Up2Error(
            diag(
                "UP2-E1006",
                f"reference {text!r} contains an empty path segment",
                fix="remove the repeated dots or the trailing dot",
                pointer=pointer,
            )
        )
    return Ref(root=parts[0], path=tuple(parts[1:]), raw=text)


def parse_path_text(text: str, /, *, pointer: str = "") -> Ref:
    """Parse bare-path text (``locals.x.y``) into a ``Ref`` (``raw`` keeps the original text).

    Used by the ``ctx`` operators: what is needed there is the **path itself** (the target to
    write or delete does not exist yet, so it cannot be handed to the reference evaluator to
    read), which is why the path is written as a literal instead of a reference.
    """
    if not isinstance(text, str) or not text:
        raise Up2Error(
            diag(
                "UP2-E1005",
                f"the path parameter must be a string, got {type(text).__name__}",
                fix='write "locals._tmp" / "globals.base_url"',
                pointer=pointer,
            )
        )
    parts = text.split(".")
    if any(part == "" for part in parts):
        raise Up2Error(
            diag(
                "UP2-E1005",
                f"path {text!r} contains an empty segment",
                fix="remove the repeated dots or the trailing dot",
                pointer=pointer,
            )
        )
    return Ref(root=parts[0], path=tuple(parts[1:]), raw=text)


@dataclass(slots=True)
class Scope:
    """The evaluation scope. ``locals`` is writable, everything else is read-only.

    ``parent`` links a nested scope to the one it was created from (one iteration of ``each``); the
    fallback is outward while a write stays where it was asked for. The rule is **by name**: the
    innermost scope holding the first segment of a path resolves the whole path, so a name this
    scope wrote is never resolved in a parent, however deep the path goes.

    ``step_input`` is the value ``$in`` names: the input of the **story step** being evaluated (a
    field chain inside one step still sees the step's input, never the element ``each`` handed it).
    It stays ``MISSING`` when nothing was handed in.
    """

    globals: Mapping[str, Any] = field(default_factory=dict)
    products: Mapping[str, Any] = field(default_factory=dict)
    locals: dict[str, Any] = field(default_factory=dict)
    parent: Scope | None = None
    step_input: Any = MISSING

    def child(self) -> Scope:
        """A fresh scope for one iteration: same globals/products/input, outward reads."""
        return Scope(
            globals=self.globals,
            products=self.products,
            parent=self,
            step_input=self.step_input,
        )

    def read(self, ref: Ref) -> Outcome:
        """Read a reference.

        An absent key is ``Missing``; a structure shallower than declared is ``Failed(E2001)``.
        A ``locals``/``fields`` read walks outward by name: the innermost scope holding the first
        segment of the path resolves the whole path.
        """
        if ref.root == "globals":
            return _walk_path(self.globals, ref)
        if ref.root in _LOCAL_ALIASES:
            return self._read_locals(ref)
        if ref.root == INPUT_ROOT:
            if self.step_input is MISSING:
                return Missing(
                    reason=f"{ref.raw} names this step's input, and no input was handed to it"
                )
            return _walk_path(self.step_input, ref)
        product = self.products.get(ref.root)
        if product is None:
            return Failed(
                code="UP2-E2001",
                reason=f"there is no earlier node product named {ref.root!r}",
                fix="check the node key, or inject it with --product",
            )
        return _walk_path(product, ref)

    def _read_locals(self, ref: Ref) -> Outcome:
        """Walk outward until a scope owns the first segment; the innermost owner decides."""
        scope = self
        while scope.parent is not None and ref.path and ref.path[0] not in scope.locals:
            scope = scope.parent
        return _walk_path(scope.locals, ref)

    def read_text(self, text: str, /, *, pointer: str = "") -> Outcome:
        """Read by bare-path text (used by ctx.get / ctx.map)."""
        return self.read(parse_path_text(text, pointer=pointer))

    def write_text(self, text: str, value: Any, /, *, pointer: str = "") -> None:
        """Write into the current field scope by bare-path text.

        A non-writable root is a programming error.
        """
        ref = parse_path_text(text, pointer=pointer)
        if ref.root not in _LOCAL_ALIASES:
            raise ValueError(f"{text!r} is not a writable path (only locals/fields roots allowed)")
        self.write_local(ref.path, value)

    def delete_text(self, text: str, /, *, pointer: str = "") -> bool:
        """Delete by bare-path text; return whether something was deleted."""
        ref = parse_path_text(text, pointer=pointer)
        return self.delete_local(ref.path)

    def json_view(self) -> dict[str, dict[str, Any]]:
        """The **JSON projection** of the scope: ``{"locals": {...}, "globals": {...}}``.

        The ``locals`` view is resolved along the scope lineage (outermost first, the innermost
        winning), so in-chain code and host functions see the same name a reference read sees.

        Non-JSON values (``Opaque`` node handles, for example) are **dropped** rather than
        reported as an error -- they could never leave the chain anyway (``UP2-E2003``), so in-chain
        code not seeing them follows the same principle instead of being a new silent drop.
        """
        merged: dict[str, Any] = {}
        for outer in self._lineage():
            merged.update(outer.locals)
        view: dict[str, dict[str, Any]] = {}
        for partition in CTX_PARTITIONS:
            source: Mapping[str, Any] = merged if partition in _LOCAL_ALIASES else self.globals
            view[partition] = {key: value for key, value in source.items() if is_json_value(value)}
        return view

    def _lineage(self) -> tuple[Scope, ...]:
        """The scope lineage, outermost first."""
        scopes: list[Scope] = []
        scope: Scope | None = self
        while scope is not None:
            scopes.append(scope)
            scope = scope.parent
        scopes.reverse()
        return tuple(scopes)

    def write_local(self, path: tuple[str, ...], value: Any) -> None:
        """Write into the current field scope (``locals``), creating dicts as needed."""
        target = self.locals
        for segment in path[:-1]:
            nxt = target.get(segment)
            if not isinstance(nxt, dict):
                nxt = {}
                target[segment] = nxt
            target = nxt
        target[path[-1]] = value

    def delete_local(self, path: tuple[str, ...]) -> bool:
        """Delete a path in the current field scope; return whether something was deleted."""
        target = self.locals
        for segment in path[:-1]:
            nxt = target.get(segment)
            if not isinstance(nxt, dict):
                return False
            target = nxt
        return target.pop(path[-1], _SENTINEL) is not _SENTINEL


def _walk_path(base: Any, ref: Ref) -> Outcome:
    """Walk a reference path, dispatching on the value kind.

    A mapping is read by key, a sequence by index and a **host object by ``getattr``**, so one
    dotted path works on a dictionary and on an object alike. An absent key is ``Missing`` (the
    value is not there); a structure that cannot take the segment - a scalar, an index out of
    range, or an object without that attribute - is ``Failed`` (``UP2-E2001``), and the reason
    names the class the walk hit.
    """
    current = base
    walked: list[str] = []
    for segment in ref.path:
        outcome = _descend(current, segment, ref, walked)
        if not isinstance(outcome, Ok):
            return outcome
        current = outcome.value
        walked.append(segment)
    return Ok(current)


def _descend(current: Any, segment: str, ref: Ref, walked: list[str]) -> Outcome:
    """Take one path segment from a mapping, a sequence or a host object."""
    if isinstance(current, Mapping):
        if segment not in current:
            return Missing(
                reason=f"{ref.raw} is missing key {segment!r} at {'.'.join(walked) or ref.root}"
            )
        return Ok(current[segment])
    if isinstance(current, (list, tuple)):
        return _walk_sequence(current, segment, ref)
    if current is None or isinstance(current, (str, bool, int, float)):
        return Failed(
            code="UP2-E2001",
            reason=f"{ref.raw} hit {type_name(current)} at "
            f"{'.'.join(walked) or ref.root} and cannot continue to {segment!r}",
            fix="check how deep the reference path is, or add the intermediate fields",
        )
    return _walk_attribute(current, segment, ref, walked)


def _walk_sequence(current: list[Any] | tuple[Any, ...], segment: str, ref: Ref) -> Outcome:
    """Index a sequence with a dotted segment; only digits are an index."""
    try:
        index = int(segment)
    except ValueError:
        return Failed(
            code="UP2-E2001",
            reason=f"{ref.raw} tried to index a list with {segment!r}",
            fix='a sequence is read by a digit index; for anything else use ["py","getitem",K]',
        )
    try:
        return Ok(current[index])
    except IndexError:
        return Failed(
            code="UP2-E2001",
            reason=f"{ref.raw} is out of range: the list has {len(current)} items, so index "
            f"{index} cannot be read",
            fix="check the length of the list, or take an element with py.first / py.last",
        )


def _walk_attribute(current: Any, segment: str, ref: Ref, walked: list[str]) -> Outcome:
    """Read an attribute of a host object; the reason carries the exception's own class name."""
    try:
        return Ok(getattr(current, segment))
    except AttributeError as exc:
        return Failed(
            code="UP2-E2001",
            reason=f"{ref.raw} at {'.'.join(walked) or ref.root}: {exc.__class__.__name__}: {exc}",
            fix="check the attribute name against the host object, or read it with "
            '["py","getattr",NAME]',
        )


_SENTINEL: Final = object()
