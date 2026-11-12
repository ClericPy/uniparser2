"""``css`` / ``css1`` operators: CSS selectors (design doc 02 §6.1).

**Slots** (see ``02`` §1, uniform across operators): ``["css1", accessor, selector]`` — the
accessor is in slot 2 and the operand (the selector) in slot 3. The two operators differ only in
cardinality:

| accessor | ``css`` (all matches) | ``css1`` (the first only) |
|---|---|---|
| ``text`` / ``html`` / ``outer`` / ``@<attr>`` | ``list[str]`` | scalar, else empty |
| ``nodes`` | ``list[Opaque]`` (all) | ``list[Opaque]`` (0 or 1) |
| ``self`` | ``Opaque`` (the first; use ``nodes`` for all) | ``Opaque`` |
| ``remove`` | a **copy** with every match pruned | a copy with the **first** match pruned |

**Why two operators instead of one operator plus a parameter** (the conclusion after weighing it
repeatedly while finishing L1):

- **Both cardinalities are explicit, and neither has a silent default.** Turning it into "first by
  default + an `all: true` switch" means forgetting the switch yields a **legal but first-only**
  value — a silent truncation, which conflicts with "bad things stay loud"; with two operators,
  choosing wrong is reported loudly as ``UP2-E2002``.
- **``nodes`` cannot carry "take all values"**: it hands out ``Opaque`` handles, and within L1 the
  only thing to do with them is count them with ``py.len`` (taking text means applying per item,
  which is L2 fan-out). Its job is **to hand a node set to L2 fan-out** (extracting title+href
  from every ``<li>`` requires handles), not to take values.
- **The action table is shared**, so the code delta for "two operators" is one ``first_only`` flag,
  not two action vocabularies.
- Cardinality lives in the **operator name** (`css` = all, `css1` = first), rather than giving the
  accessor yet another "how many" parameter: the accessor is a **closed enumeration**, and stuffing
  compound keys such as ``$1:text`` into it amounts to treating a closed enumeration as an open
  namespace.

**The performance rationale for ``css1`` must be stated accurately**: it is not faster because of
the engine's ``css_first`` — measured, ``css_first`` costs the same as ``css`` (1.0–1.1x at
5000–20000 matches), because matching itself has to walk the whole tree. The real gain is in the
**extraction stage**: only the first is extracted by default, so the N-1 texts/attributes that
would be discarded afterwards need not be extracted at all (measured, ``text`` over 5000 ``<a>``:
4.25 ms vs 108.9 ms).

Four implementation disciplines:

1. **``remove`` is pure** (``02`` §D-02-3): it returns a pruned copy and only affects this field's
   chain. Deleting in place would let one item's operation pollute the next when the same document
   is parsed item by item. It is also the contract the run-scoped materialization cache rests on
   (`03` §6): a cached document MUST NOT be mutated, so ``remove`` and ``text`` (which needs the
   noise tags stripped) both work on a copy.
2. **Nodes are always wrapped in ``DomNode(Opaque)``**: native engine objects never enter the value
   domain, so the output of ``nodes`` / ``self`` is naturally rejected by export boxing
   (``UP2-E2003``).
3. **``text`` excludes the text of ``script``/``style``/``noscript``** (the noise set of ``remove``
   in the ``04`` draft): this is **the semantics this operator promises** and does not rely on
   engine defaults (selectolax's ``text()`` would include them).
4. **The input is a ``str`` or a node**; a list input reports ``UP2-E2002`` — per-item parsing
   belongs to the chain-level structure (``each``), and doing it here only yields a concatenation of
   unclear semantics.
5. **Write attribute names in lowercase** (``@href``, not ``@HREF``): HTML attribute names are
   themselves case-insensitive, but the engine's ``.attributes`` keys are already normalized to
   lowercase, so ``@HREF`` finds nothing (**no** case folding is done — that would mean giving the
   action slot a lenient spelling; to fetch a value, write the canonical lowercase form).

There is exactly one engine: **selectolax** (``requires=("selectolax",)``). The former
beautifulsoup4 fallback and the ``any_requires`` "either one" mechanism have been removed: XML goes
to the ``xpath`` operator (lxml), and on HTML the two engines behave identically, so one suffices.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable, Mapping
from typing import Any, ClassVar, Final

from ..core.ast import Lit, Param
from ..core.errors import Failed, Ok, Outcome, Up2Error, diag
from ..core.materialize import HTML
from ..core.registry import ActionSpec, Call, Kind, Op, ParamSpec, op
from ..core.values import Opaque, type_name

_TEXT: Final = "text"
_HTML: Final = "html"
_OUTER: Final = "outer"
_SELF: Final = "self"
_REMOVE: Final = "remove"
_NODES: Final = "nodes"
_EXISTS: Final = "exists"
_ATTR: Final = "@<attribute>"
_SELECTOLAX: Final = "selectolax"
_HTML_EXTRA: Final = "html"
_NOISE_TAGS: Final = ("script", "style", "noscript")
"""Noise tags excluded by ``text``; they are pruned from a **copy** before the text is taken."""
_SELECTOR: Final = ParamSpec("selector", Kind.LITERAL)
_ACTIONS: Final[Mapping[str, ActionSpec]] = {
    _TEXT: ActionSpec(_TEXT, "plain text", (_SELECTOR,)),
    _HTML: ActionSpec(_HTML, "inner HTML", (_SELECTOR,)),
    _OUTER: ActionSpec(_OUTER, "outer HTML", (_SELECTOR,)),
    _SELF: ActionSpec(_SELF, "the node handle itself", (_SELECTOR,)),
    _NODES: ActionSpec(_NODES, "the set of matching nodes", (_SELECTOR,)),
    _EXISTS: ActionSpec(_EXISTS, "whether the selector matches at least one node", (_SELECTOR,)),
    _REMOVE: ActionSpec(_REMOVE, "a copy with the matching nodes pruned", (_SELECTOR,)),
    _ATTR: ActionSpec(_ATTR, "attribute value", (ParamSpec("attr", Kind.LITERAL), _SELECTOR)),
}


class DomNode(Opaque):
    """Unified wrapper around engine nodes.

    It can flow through the chain, but the export must be rejected (``UP2-E2003``).
    """

    __slots__ = ("raw",)

    def __init__(self, raw: Any) -> None:
        self.raw = raw

    def __repr__(self) -> str:
        return f"<DomNode {type(self.raw).__name__}>"


def _html_parser() -> Any:
    """The lexbor parser class (selectolax >= 1.0).

    selectolax 1.0 removed the modest ``selectolax.parser`` backend. The lexbor class exposes every
    method this adapter uses (``css`` / ``css_first`` / ``text`` / ``html`` / ``attributes`` /
    ``decompose`` / ``strip_tags`` / ``iter(include_text=)``).
    """
    return importlib.import_module("selectolax.lexbor").LexborHTMLParser


class SelectolaxEngine:
    """selectolax adapter layer.

    **Three API facts hit by measurement** (writing from old memory gets them wrong): ``Node`` has
    no ``clone()`` and no ``outer_html``; ``node.html`` returns the **outer** HTML. So "take a
    copy" can only re-parse ``node.html``, and "inner HTML" can only concatenate the ``html`` of
    the direct children.
    """

    name = _SELECTOLAX

    def __init__(self) -> None:
        self._HTMLParser = _html_parser()

    def parse(self, text: str) -> Any:
        return self._HTMLParser(text)

    def size(self, document: Any) -> int:
        """The document's materialized size in bytes, for the run-scoped cache (`03` §6).

        A selectolax tree lives in the C extension: the Python object is a 96-byte handle whatever
        the document's size is (measured), so ``sys.getsizeof`` measures nothing. The document's own
        markup is the measure that tracks the tree — measured, a DOM costs ~24x its text in resident
        memory, and the serialization grows with the same node count. It is computed once per
        materialization (a miss), against a parse of the same text.
        """
        return len(str(document.html or "").encode("utf-8"))

    def copy(self, node: Any) -> Any:
        return self._HTMLParser(node.html)

    def select(self, node: Any, selector: str) -> list[Any]:
        return list(node.css(selector))

    def text(self, node: Any) -> str:
        copy = self.copy(node)
        copy.strip_tags(list(_NOISE_TAGS))
        return str(copy.text() or "")

    def inner_html(self, node: Any) -> str:
        if not hasattr(node, "iter"):  # the root has no "inner"; return the whole document
            return str(node.html or "")
        return "".join(child.html for child in node.iter(include_text=True))

    def outer_html(self, node: Any) -> str:
        return str(node.html or "")

    def attr(self, node: Any, name: str) -> str | None:
        value = node.attributes.get(name)
        return None if value is None else str(value)

    def select_first(self, node: Any, selector: str) -> Any | None:
        return node.css_first(selector)

    def prune(self, node: Any, selector: str, *, first_only: bool = False) -> Any:
        copy = self.copy(node)
        matched = copy.css(selector)
        for target in matched[:1] if first_only else matched:
            target.decompose()
        return copy

    def validate(self, selector: str) -> None:
        self.parse("<html></html>").css(selector)


def engine() -> SelectolaxEngine | None:
    """The engine an operator builds with; ``None`` when selectolax is missing.

    There is nothing to cache between runs here: the adapter is an import (a module lookup) plus an
    object, while the **document** it parses is what the run-scoped cache of `03` §6 holds.
    """
    try:
        return SelectolaxEngine()
    except ImportError:
        return None


class _SelectorOp(Op):
    """Shared implementation of ``css`` / ``css1``; the only difference is the ``first_only`` flag.

    The action table is **shared** (the same ``_ACTIONS``), so the code delta for "two operators"
    is just this one flag: cardinality lives in the operator name, so the action vocabulary need
    not be duplicated.
    """

    requires = (_SELECTOLAX,)
    slot_roles = ("accessor", "selector")
    actions: ClassVar[Mapping[str, ActionSpec]] = _ACTIONS
    first_only: ClassVar[bool] = False

    def resolve_action(self, action_text: Any, *, pointer: str = "") -> str:
        text = action_text if isinstance(action_text, str) else repr(action_text)
        if text.startswith("@"):
            if len(text) == 1:
                raise Up2Error(
                    diag(
                        "UP2-E1002",
                        "an attribute name must follow `@`",
                        fix='write "@href" / "@content"',
                        pointer=pointer,
                        allowed=tuple(sorted(self.actions)),
                    )
                )
            return _ATTR
        return super().resolve_action(text, pointer=pointer)

    def action_params(self, action: str, action_text: Any) -> Mapping[str, Param]:
        if action != _ATTR:
            return {}
        return {"attr": Lit(str(action_text)[1:])}

    def precompile(self, action: str, params: Mapping[str, Param], *, pointer: str = "") -> Any:
        del action
        active = engine()
        if active is None:  # pragma: no cover - the dependency gate already blocks this
            return None
        selector = _literal(params, "selector", pointer=f"{pointer}/selector")
        if not selector:
            return None  # empty string = the current node itself (not a CSS selector)
        try:
            active.validate(selector)
        except Exception as exc:
            raise Up2Error(
                diag(
                    "UP2-E1005",
                    f"invalid CSS selector: {exc}",
                    fix='fix the selector; an empty string means "the current node itself"',
                    pointer=f"{pointer}/selector",
                )
            ) from exc
        return None

    def evaluate(self, call: Call) -> Outcome:
        active = engine()
        if active is None:
            return Failed(
                code="UP2-E1107",
                reason="css needs selectolax",
                fix=f'install it: uv add "uniparser2[{_HTML_EXTRA}]"',
            )
        context = _context_doc(active, call)
        if isinstance(context, Failed):
            return context
        selector = str(call.params.get("selector") or "")
        raw = context.raw
        if call.action == _REMOVE:
            return _prune(active, context, selector, first_only=self.first_only)
        matched = _select(active, raw, selector, first_only=self.first_only)
        if call.action == _EXISTS:
            # A boolean, so no predicate has to reason about an empty value.
            return Ok(bool(matched))
        if call.action in (_SELF, _NODES):
            return _node_result(call.action, matched)
        return _value_result(active, call, matched, first_only=self.first_only)


@op("css")
class Css(_SelectorOp):
    """Take **all** matches: value actions yield a ``list``, ``remove`` prunes every match."""

    summary = "CSS selector (all matches)"


@op("css1")
class Css1(_SelectorOp):
    """Take only the **first** match: value actions yield a scalar, ``remove`` prunes the first."""

    summary = "CSS selector (first match only)"
    first_only = True


def _select(active: SelectolaxEngine, raw: Any, selector: str, *, first_only: bool) -> list[Any]:
    """An empty selector ⇒ the current node itself; ``first_only`` uses the engine's ``css_first``.

    Note: ``css_first`` is **not faster than** ``css`` (measured 1.0–1.1x at 5000–20000 matches,
    because matching itself has to walk the whole tree). It is used to express intent; the real
    gain of "first only" is in the **extraction stage** — the N-1 texts/attributes that would be
    discarded afterwards are never extracted (measured, ``text`` over 5000 matches: 4.25 ms vs
    108.9 ms).
    """
    if selector == "":
        return [raw]
    if first_only:
        found = active.select_first(raw, selector)
        return [] if found is None else [found]
    return active.select(raw, selector)


def _literal(params: Mapping[str, Param], name: str, *, pointer: str = "") -> str:
    value = params[name]
    text = value.value if isinstance(value, Lit) else value
    if not isinstance(text, str):
        raise Up2Error(
            diag(
                "UP2-E1005",
                f"parameter {name!r} must be a string, got {type_name(text)}",
                fix="write selector as a CSS selector string (empty string = the current node)",
                pointer=pointer or f"/1/{name}",
            )
        )
    return text


def _context_doc(active: SelectolaxEngine, call: Call) -> Any:
    """Normalize the input into a context node.

    A string is **materialized through the run's cache** (`03` §6), a ``DomNode`` is unwrapped, and
    anything else reports ``UP2-E2002``. The cached document is never mutated: the wrapping
    ``DomNode`` is fresh per call, and every action that would change the tree works on a copy
    (``remove`` and ``text`` both do).
    """
    value = call.value
    if isinstance(value, str):
        return DomNode(_document(active, call, value))
    if isinstance(value, DomNode):
        return value
    return Failed(
        code="UP2-E2002",
        reason=f"css needs a str or a node input, got {type_name(value)}",
        fix='per-item parsing belongs to the chain level: ["css","nodes",S] then ["each",{...}]',
    )


def _document(active: SelectolaxEngine, call: Call, text: str) -> Any:
    """The HTML document for ``text``: one parse per run, through the materializer (`03` §6)."""

    def build(source: str) -> tuple[Any, int]:
        document = active.parse(source)
        return document, active.size(document)

    return call.cache.get(HTML, text, build)


def _prune(
    active: SelectolaxEngine, context: DomNode, selector: str, *, first_only: bool
) -> Outcome:
    """``remove`` returns a pruned **copy** (pure); an empty selector prunes nothing."""
    if selector == "":
        return Ok(context)
    try:
        return Ok(DomNode(active.prune(context.raw, selector, first_only=first_only)))
    except Exception as exc:
        return Failed(code="UP2-E2005", reason=f"remove failed: {exc}")


def _node_result(action: str, matched: list[Any]) -> Outcome:
    if not matched:
        # The empty value of the shape: a node set is a list, a single handle is absent (null).
        return Ok([] if action == _NODES else None)
    if action == _NODES:
        return Ok([DomNode(node) for node in matched])
    return Ok(DomNode(matched[0]))


def _value_result(
    active: SelectolaxEngine, call: Call, matched: list[Any], *, first_only: bool
) -> Outcome:
    values: list[str] = []
    for node in matched:
        if call.action == _ATTR:
            found = active.attr(node, str(call.params["attr"]))
            if found is None:
                continue
            values.append(found)
            continue
        values.append(_EXTRACTORS[call.action](active, node))
    if first_only:
        return Ok(values[0] if values else "")
    return Ok(values)


_EXTRACTORS: Final[Mapping[str, Callable[[SelectolaxEngine, Any], str]]] = {
    _TEXT: lambda active, node: active.text(node),
    _HTML: lambda active, node: active.inner_html(node),
    _OUTER: lambda active, node: active.outer_html(node),
}
