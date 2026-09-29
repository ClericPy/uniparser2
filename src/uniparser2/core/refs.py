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
- ``item``: the iteration variable inside a ``$map`` template, available in L2 only.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from .ast import Ref
from .errors import Failed, Missing, Ok, Outcome, Up2Error, diag
from .values import is_json_value, type_name

REF_PREFIX: Final = "$"
LIT_DIRECTIVE: Final = "$lit"
RESERVED_ROOTS: Final = ("globals", "locals", "fields", "item")
WRITABLE_ROOTS: Final = ("locals", "fields")
# In L1, $fields and $locals name the scope of the current field; $item waits for $map (L2).
_LOCAL_ALIASES: Final = ("locals", "fields")
_DEFERRED_ROOTS: Final = ("item",)
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
    """The evaluation scope. ``locals`` is writable, everything else is read-only."""

    globals: Mapping[str, Any] = field(default_factory=dict)
    products: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    locals: dict[str, Any] = field(default_factory=dict)

    def read(self, ref: Ref) -> Outcome:
        """Read a reference.

        An absent key is ``Missing``; a structure shallower than declared is ``Failed(E2001)``.
        """
        base: Any
        if ref.root == "globals":
            base = self.globals
        elif ref.root in _LOCAL_ALIASES:
            base = self.locals
        else:
            product = self.products.get(ref.root)
            if product is None:
                return Failed(
                    code="UP2-E2001",
                    reason=f"there is no earlier node product named {ref.root!r}",
                    fix="check the node key, or inject it with --product",
                )
            base = product
        current = base
        walked: list[str] = []
        for segment in ref.path:
            if isinstance(current, Mapping):
                if segment not in current:
                    return Missing(
                        reason=f"{ref.raw} is missing key {segment!r} at "
                        f"{'.'.join(walked) or ref.root}"
                    )
                current = current[segment]
            elif isinstance(current, list):
                return Failed(
                    code="UP2-E2001",
                    reason=f"{ref.raw} tried to index a list with {segment!r}",
                    fix='references do not support array subscripts, use ["py","getitem",N]',
                )
            else:
                return Failed(
                    code="UP2-E2001",
                    reason=f"{ref.raw} hit {type_name(current)} at "
                    f"{'.'.join(walked) or ref.root} and cannot continue to {segment!r}",
                    fix="check how deep the reference path is, or add the intermediate fields",
                )
            walked.append(segment)
        return Ok(current)

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

        Non-JSON values (``Opaque`` node handles, for example) are **dropped** rather than
        reported as an error -- they could never leave the chain anyway (``UP2-E2003``), so in-chain
        code not seeing them follows the same principle instead of being a new silent drop.
        """
        view: dict[str, dict[str, Any]] = {}
        for partition in CTX_PARTITIONS:
            source: Mapping[str, Any] = self.locals if partition in _LOCAL_ALIASES else self.globals
            view[partition] = {key: value for key, value in source.items() if is_json_value(value)}
        return view

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


_SENTINEL: Final = object()
