"""Reference syntax and scope (design doc 02 §3, 03 §8).

One rule covers everything: **a leading ``$`` means a reference; a ``$``-prefixed literal is
written ``{"$lit": ...}``; everything else is a literal.**
(Whether a string counts as a reference is decided by the parameter kind, see
``core.registry.Kind``.)

Scope (L1):
- ``globals``: the chain-level read-only environment.
- ``locals``: the scope of the current field (writable).
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
from .errors import Failed, Ok, Outcome, Up2Error, diag
from .materialize import Materializer
from .values import is_json_value, type_name

_NO_STEP_INPUT: Final = object()
"""Marks "no step input was handed in"; a read of ``$in`` then fails instead of yielding a value."""

REF_PREFIX: Final = "$"
LIT_DIRECTIVE: Final = "$lit"
RESERVED_ROOTS: Final = ("globals", "locals", "public", "in", "obj")
WRITABLE_ROOTS: Final = ("locals", "public")
INPUT_ROOT: Final = "in"
"""The root naming **this node invocation's input** (``$in.url``, design doc 03 §2.1).

A node invocation's input is the value the caller handed over (the stage value before a
``["node", name]`` call, or the run's own input at the top), and it has no ``locals`` round-trip:
``$in`` names it.
"""
OBJ_ROOT: Final = "obj"
"""The root naming **the value the current stage received** (design D11/D14).

It is not a scope: it takes no path and is resolved from the stage's ``Call`` rather than from a
``Scope``. The same value is readable through ``ctx`` as ``obj``.
"""
PUBLIC_ROOT: Final = "public"
"""The root naming the **run's shared scope** (``$public.page``, change `public-scope-and-try`).

The three scopes read as constants / shared / private: ``globals`` is the chain's read-only
constants (fingerprinted), ``public`` is the run's own notes (writable, never fingerprinted), and
``locals`` is private to the scope that wrote it.
"""
# `locals` is the scope of the current field: the step's `_`-prefixed keys, plus each iteration's
# own scratch area. `$fields` was a second name for the same namespace and is retired (change
# `rename-and-unify`): one namespace, one spelling.
CTX_PARTITIONS: Final = ("locals", "globals", "public")
"""The partitions the scope exposes (``ctx.locals`` / ``ctx.globals`` / ``ctx.public``, 01 Q40).

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

    ``step_input`` is the value ``$in`` names: the input of the **node invocation** being evaluated
    (a field chain inside one node still sees the node's input, never the element ``each`` handed
    it). It stays unset when nothing was handed in, and a read of ``$in`` then fails
    (`UP2-E2001`).

    ``iteration`` is which fan-out result this scope evaluates: the ordinal its fan-out operator
    gave it for that element, or ``None`` at the top of a run. The trace reports it as ``item``
    (`06` §5.1), which is what makes "the third result's title is missing" locatable.

    ``cache`` is the run's materialization cache (`03` §6), reached through :attr:`materializer`.
    It is created lazily by the scope that first needs it and shared down the lineage, so every
    operator of one run reaches the same cache and the cache is released with the run: a scope that
    materializes nothing never pays for one.
    """

    globals: Mapping[str, Any] = field(default_factory=dict)
    products: Mapping[str, Any] = field(default_factory=dict)
    locals: dict[str, Any] = field(default_factory=dict)
    public: dict[str, Any] = field(default_factory=dict)
    """The run's **shared** scope: writable from any node, readable from any node.

    It is **not** chain data, so it never enters the fingerprint: the run's notes are runtime state,
    not a property of the chain. The run's root scope owns it and every child scope shares it by
    reference, so a value written inside an ``each`` element is still there after the element.
    """
    udfs: Mapping[str, Any] = field(default_factory=dict)
    """The run's udf table (process-wide defaults plus the run's overlay), shared by every scope."""
    types: Mapping[str, Any] = field(default_factory=dict)
    """The run's type table (process-wide registry plus the run's overlay), shared by every scope.

    A `type` stage reads it, so ``run(..., types={...})`` reaches the stage without a second
    parameter through the evaluator (``03`` §3.2).
    """
    parent: Scope | None = None
    step_input: Any = _NO_STEP_INPUT
    iteration: int | None = None
    cache: Materializer | None = field(default=None, init=False, repr=False, compare=False)
    """The run's materialization cache (`03` §6); :attr:`materializer` owns every access to it."""

    @property
    def materializer(self) -> Materializer:
        """The run's materialization cache, created on first use (`03` §6).

        The nearest scope of the lineage that already holds one answers; otherwise this scope
        becomes the owner, which makes the cache's lifetime the lineage's lifetime.
        """
        scope: Scope | None = self
        while scope is not None:
            if scope.cache is not None:
                return scope.cache
            scope = scope.parent
        created = Materializer()
        self.cache = created
        return created

    def child(self, iteration: int | None = None) -> Scope:
        """A fresh scope for one iteration: same globals/products/input, outward reads.

        ``iteration`` is the fan-out operator's own ordinal for this element — `each` walks its list
        in input order, so it passes the element's position, which is the fan-out index the trace
        reports (`06` §5.1). A caller with no fan-out position leaves it out.
        """
        return Scope(
            globals=self.globals,
            products=self.products,
            public=self.public,
            udfs=self.udfs,
            types=self.types,
            parent=self,
            step_input=self.step_input,
            iteration=iteration,
        )

    def read(self, ref: Ref) -> Outcome:
        """Read a reference.

        An absent key is ``Failed(E2001)``; a structure shallower than declared is also
        ``Failed(E2001)``. A ``locals`` read walks outward by name: the innermost scope holding the
        first segment of the path resolves the whole path.
        """
        if ref.root == "globals":
            return _walk_path(self.globals, ref)
        if ref.root == "locals":
            return self._read_locals(ref)
        if ref.root == PUBLIC_ROOT:
            return _walk_path(self.public, ref)
        if ref.root == INPUT_ROOT:
            if self.step_input is _NO_STEP_INPUT:
                return Failed(
                    code="UP2-E2001",
                    reason=(
                        f"{ref.raw} names this node invocation's input, "
                        "and no input was handed to it"
                    ),
                    fix="hand the run a value, or write the step that produces this input",
                )
            return _walk_path(self.step_input, ref)
        if ref.root == OBJ_ROOT:
            return Failed(
                code="UP2-E2001",
                reason=f"{ref.raw} names the value a stage received, and a scope cannot read it",
                fix='read "$obj" in a stage parameter; a whole-chain reference names a scope',
            )
        product = self.products.get(ref.root, _ABSENT)
        if product is _ABSENT:
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
        """Read by bare-path text (used by ctx.get / ctx.dict / ctx.list)."""
        return self.read(parse_path_text(text, pointer=pointer))

    def write_text(self, text: str, value: Any, /, *, pointer: str = "") -> None:
        """Write into a writable scope by bare-path text.

        A non-writable root is a programming error.
        """
        ref = parse_path_text(text, pointer=pointer)
        if ref.root == "locals":
            self.write_local(ref.path, value)
            return
        if ref.root == PUBLIC_ROOT:
            self.write_public(ref.path, value)
            return
        raise ValueError(
            f"{text!r} is not a writable path (only {', '.join(WRITABLE_ROOTS)} are writable)"
        )

    def delete_text(self, text: str, /, *, pointer: str = "") -> bool:
        """Delete by bare-path text; return whether something was deleted."""
        ref = parse_path_text(text, pointer=pointer)
        if ref.root == "locals":
            return self.delete_local(ref.path)
        if ref.root == PUBLIC_ROOT:
            return self.delete_public(ref.path)
        raise ValueError(
            f"{text!r} is not a writable path (only {', '.join(WRITABLE_ROOTS)} are writable)"
        )

    def json_view(self) -> Outcome:
        """The **JSON projection** of the scope: ``{"locals": …, "globals": …, "public": …}``.

        The ``locals`` view is resolved along the scope lineage (outermost first, the innermost
        winning), so in-chain code and host functions see the same name a reference read sees.

        A value that is not JSON is **reported, not dropped**: silently removing a name would make
        in-chain code see a variable that "was never set" while it plainly was, which is exactly the
        kind of hidden rule this engine does not have. The failure names every offending key and
        shows its ``repr``, so the fix (convert the handle to text first) is obvious from the error.
        """
        merged: dict[str, Any] = {}
        for outer in self._lineage():
            merged.update(outer.locals)
        view: dict[str, dict[str, Any]] = {}
        offenders: list[str] = []
        for partition in CTX_PARTITIONS:
            if partition == "locals":
                source: Mapping[str, Any] = merged
            elif partition == "public":
                source = self.public
            else:
                source = self.globals
            kept: dict[str, Any] = {}
            for key, value in source.items():
                if is_json_value(value):
                    kept[key] = value
                else:
                    offenders.append(f"{partition}.{key} = {value!r}")
            view[partition] = kept
        if offenders:
            return Failed(
                code="UP2-E2009",
                reason=(
                    "the JSON projection of the scope holds "
                    f"{len(offenders)} value(s) that are not JSON: {'; '.join(offenders)}"
                ),
                fix="convert each value to text or a JSON shape first, then write it back "
                "with ctx.set (a consumer that takes JSON only is what reads this projection)",
            )
        return Ok(view)

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

    def write_public(self, path: tuple[str, ...], value: Any) -> None:
        """Write into the run's shared scope (``public``), creating dicts as needed."""
        target = self.public
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

    def delete_public(self, path: tuple[str, ...]) -> bool:
        """Delete a path in the run's shared scope; return whether something was deleted."""
        target = self.public
        for segment in path[:-1]:
            nxt = target.get(segment)
            if not isinstance(nxt, dict):
                return False
            target = nxt
        return target.pop(path[-1], _SENTINEL) is not _SENTINEL


def _walk_path(base: Any, ref: Ref) -> Outcome:
    """Walk a reference path, dispatching on the value kind.

    A mapping is read by key, a sequence by index and a **host object by ``getattr``**, so one
    dotted path works on a dictionary and on an object alike. An absent key, a scalar that cannot
    take the segment, an index out of range and an object without that attribute are all
    ``Failed`` (``UP2-E2001``), and the reason names what the walk hit.
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
            return Failed(
                code="UP2-E2001",
                reason=f"{ref.raw} is missing key {segment!r} at {'.'.join(walked) or ref.root}",
                fix="read a key the value has, or make the producing stage write it",
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
    """Read an attribute of a host object; the reason carries the exception's own class name.

    A **callable** attribute is read like any other: ``getattr`` reads, it does not call, so
    ``$resp.json`` resolves to the bound method and hands it on. Whether that is useful is the
    caller's judgement -- the engine does not refuse a value because it anticipates a problem
    (``AGENTS.md``, "Determinism: what you see is what you get").
    """
    try:
        found = getattr(current, segment)
    except AttributeError as exc:
        return Failed(
            code="UP2-E2001",
            reason=f"{ref.raw} at {'.'.join(walked) or ref.root}: {exc.__class__.__name__}: {exc}",
            fix="check the attribute name against the host object, or read it with "
            '["py","getattr",NAME]',
        )
    return Ok(found)


_SENTINEL: Final = object()
_ABSENT: Final = object()
"""Marks "the root is not in the product table"; a product whose value is ``None`` is a value."""
