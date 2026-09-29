"""``xpath`` operator: XPath queries (design doc 02 §6.11); **its home turf is XML**.

Why XML does not use ``css``: measured, selectolax raises ``ValueError: Bad CSS Selectors`` on XML
with prefixed namespaces (``dc|creator``), the unprefixed spelling fetches nothing
(``dc\\:creator`` → ``[]``), and it merges ``<Item>`` and ``<item>`` into the same element. CSS
naturally has to work around XML namespaces, while XPath is XML's native language:
``//dc:creator`` plus one mapping is enough, and CDATA, case sensitivity and self-closing tags are
all handled correctly.

**Two pitfalls found by measurement, which this operator turns into readable diagnostics**:

1. **Default namespace**: for a document such as ``<urlset xmlns="http://www.sitemaps.org/...">``
   (which sitemaps are), ``//loc`` **silently returns empty** (no error). When the result is empty
   this operator points this out in ``Missing`` and offers two fixes:
   ``//*[local-name()='loc']`` and an ``ns`` mapping.
2. **Undefined prefix**: ``//dc:creator`` without ``ns`` makes lxml raise
   ``XPathEvalError: Undefined namespace prefix``. Measured, that error appears **only at
   evaluation time** (not at construction time), so compile time runs the expression once against
   an empty document to bring prefix/function-name errors — which do not depend on the document —
   forward to compile time (``UP2-E1005``, consistent with the kernel invariant "a bad chain fails
   at compile time").

**Slots** (see ``02`` §1, uniform across operators): ``["xpath", accessor, XPath expression]`` —
the accessor is in slot 2 and the operand (the expression) in slot 3. When the expression needs a
namespace mapping, slot 3 holds an object ``{"expr": …, "ns": {…}}``.

**There are only three accessors** (the value is always a ``list``; ask for a scalar by chaining
``py.first`` explicitly — the same shape rule as ``css``):

| accessor | output |
|---|---|
| ``text`` | ``list``: element descendant text (``itertext``); attributes/strings as-is |
| ``nodes`` | ``list[Opaque]`` (every matching node, for later stages to keep using) |
| ``self`` | ``Opaque`` (the first matching node; ``.//`` can select from it afterwards) |

**There is no ``@<attribute>`` accessor**: XPath can fetch attributes itself
(``//enclosure/@url`` → a list of strings), which is where it beats CSS. There is also **no**
sibling operator for "take only the first"; the rationale matches ``css`` (chain ``py.first`` for a
scalar).
"""

from __future__ import annotations

import importlib
from collections.abc import Mapping
from typing import Any, ClassVar, Final

from ..core.ast import Lit, Param
from ..core.errors import Failed, Missing, Ok, Outcome, Up2Error, diag
from ..core.registry import ActionSpec, Call, Kind, Op, ParamSpec, op
from ..core.values import Opaque, preview, type_name

_TEXT: Final = "text"
_NODES: Final = "nodes"
_SELF: Final = "self"
_LXML: Final = "lxml"
_XML_EXTRA: Final = "xml"
_NS_FIX: Final = 'provide an ns mapping, e.g. {"dc": "http://purl.org/dc/elements/1.1/"}'
_PARAMS: Final = (
    ParamSpec("expr", Kind.LITERAL),
    ParamSpec("ns", Kind.LITERAL, required=False, default=None),
)
_ACTIONS: Final[Mapping[str, ActionSpec]] = {
    _TEXT: ActionSpec(
        _TEXT, "text value (elements: all descendant text; attributes as-is)", _PARAMS
    ),
    _NODES: ActionSpec(_NODES, "the set of matching nodes", _PARAMS),
    _SELF: ActionSpec(
        _SELF, "the first matching node (relative paths can keep selecting)", _PARAMS
    ),
}


class XPathNode(Opaque):
    """XML element handle.

    It can flow through the chain, but the export must be rejected (``UP2-E2003``).
    """

    __slots__ = ("raw",)

    def __init__(self, raw: Any) -> None:
        self.raw = raw

    def __repr__(self) -> str:
        return f"<XPathNode {getattr(self.raw, 'tag', type(self.raw).__name__)}>"


def _import_lxml() -> Any:
    """Import the optional dependency lazily (a dynamic import avoids missing-module reports)."""
    return importlib.import_module("lxml.etree")


@op("xpath")
class XPath(Op):
    """XPath queries: the expression is precompiled at compile time and ``ns`` binds namespaces."""

    summary = "XPath query (XML; lxml)"
    requires = (_LXML,)
    slot_roles = ("accessor", "XPath")
    actions: ClassVar[Mapping[str, ActionSpec]] = _ACTIONS

    def precompile(self, action: str, params: Mapping[str, Param], *, pointer: str = "") -> Any:
        del action
        expr = _literal_text(params, "expr", pointer=f"{pointer}/expr")
        namespaces = _namespace_map(params, pointer=f"{pointer}/ns")
        try:
            etree = _import_lxml()
        except ImportError:  # pragma: no cover - the dependency gate (UP2-E1107) blocks this first
            return None
        try:
            compiled = etree.XPath(expr, namespaces=namespaces or None)
            # Measured: errors such as an undefined prefix or a missing function name are raised
            # **only at evaluation time** (not at construction time), so compile time runs the
            # expression once against an empty document to bring document-independent errors
            # forward to compile time.
            compiled(etree.fromstring(b"<empty/>"))
        except etree.XPathError as exc:
            raise Up2Error(
                diag(
                    "UP2-E1005",
                    f"the XPath expression is unusable: {exc}",
                    fix=f"fix expr; {_NS_FIX}",
                    pointer=f"{pointer}/expr",
                )
            ) from exc
        return compiled

    def evaluate(self, call: Call) -> Outcome:
        try:
            etree = _import_lxml()
        except ImportError:
            return Failed(
                code="UP2-E1107",
                reason="xpath needs lxml",
                fix=f'install it: uv add "uniparser2[{_XML_EXTRA}]"',
            )
        context = _context_node(etree, call.value)
        if isinstance(context, Failed):
            return context
        expr = str(call.params["expr"])
        try:
            results = list(call.payload(context))
        except etree.XPathError as exc:
            return Failed(
                code="UP2-E2005",
                reason=f"XPath evaluation failed: {exc}",
                fix=f"check expr against the document structure; {_NS_FIX}",
            )
        if not results:
            return Missing(reason=_empty_reason(context, expr))
        if call.action == _NODES:
            return _as_nodes(results)
        if call.action == _SELF:
            return _as_node(results[0])
        return Ok([_as_text(item) for item in results])


def _literal_text(params: Mapping[str, Param], name: str, *, pointer: str = "") -> str:
    value = params[name]
    text = value.value if isinstance(value, Lit) else value
    if not isinstance(text, str) or not text:
        raise Up2Error(
            diag(
                "UP2-E1005",
                f"parameter {name!r} must be a non-empty string, got {type_name(text)}",
                fix=(
                    "write expr as an XPath expression, e.g. //item/title "
                    "or //*[local-name()='loc']"
                ),
                pointer=pointer or f"/1/{name}",
            )
        )
    return text


def _namespace_map(params: Mapping[str, Param], *, pointer: str = "") -> dict[str, str]:
    """The ``ns`` parameter → prefix mapping, validated item by item into an explicit dict."""
    value = params["ns"]
    raw = value.value if isinstance(value, Lit) else value
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise _bad_namespace(pointer)
    namespaces: dict[str, str] = {}
    for key, item in raw.items():
        if not isinstance(key, str) or not isinstance(item, str):
            raise _bad_namespace(pointer)
        namespaces[key] = item
    return namespaces


def _bad_namespace(pointer: str = "") -> Up2Error:
    return Up2Error(
        diag(
            "UP2-E1005",
            "ns must be a string mapping of prefix → namespace URI",
            fix=_NS_FIX,
            pointer=pointer or "/1/ns",
        )
    )


def _context_node(etree: Any, value: Any) -> Any:
    """Normalize the input into a context node.

    XML text is parsed, an ``XPathNode`` is unwrapped, and anything else reports ``UP2-E2002``.
    """
    if isinstance(value, XPathNode):
        return value.raw
    if not isinstance(value, str):
        return Failed(
            code="UP2-E2002",
            reason=(
                f"xpath needs XML text or a node input, got {type_name(value)} "
                f"({preview(value, 40)})"
            ),
            fix="per-item parsing of a list is a chain-level structure (select / callback, L2)",
        )
    try:
        # Encode first: lxml rejects a unicode string carrying <?xml encoding=...?>.
        return etree.fromstring(value.encode("utf-8"))
    except etree.XMLSyntaxError as exc:
        return Failed(
            code="UP2-E2005",
            reason=f"XML parsing failed: {exc}",
            fix="XML must be well-formed (single root, closed tags); use css for HTML",
        )


def _is_element(value: Any) -> bool:
    return hasattr(value, "itertext")


def _as_text(item: Any) -> Any:
    """Element → all descendant text; other types (``@href``, ``count()``) are returned as-is."""
    return "".join(item.itertext()) if _is_element(item) else item


def _as_nodes(results: list[Any]) -> Outcome:
    for item in results:
        if not _is_element(item):
            return Failed(
                code="UP2-E2002",
                reason=f"nodes needs node results, got {type_name(item)} ({preview(item, 40)})",
                fix="use text for attribute/text values (e.g. //enclosure/@url)",
            )
    return Ok([XPathNode(item) for item in results])


def _as_node(item: Any) -> Outcome:
    if not _is_element(item):
        return Failed(
            code="UP2-E2002",
            reason=f"self needs node results, got {type_name(item)} ({preview(item, 40)})",
            fix="use text for attribute/text values (e.g. //enclosure/@url)",
        )
    return Ok(XPathNode(item))


def _empty_reason(context: Any, expr: str) -> str:
    """Diagnostic for an empty result: point out the default-namespace trap (sitemaps hit it)."""
    reason = f"XPath {expr!r} matched nothing"
    default_ns = _default_namespace(context)
    if default_ns is None or ":" in expr:
        return reason
    return (
        f"{reason}. Note: the document root carries the default namespace xmlns={default_ns!r}, "
        "so unprefixed names cannot match it — use //*[local-name()='name'], or add a prefix to "
        "the ns mapping"
    )


def _default_namespace(context: Any) -> str | None:
    try:
        nsmap = context.getroottree().getroot().nsmap
    except Exception:  # failing to get nsmap only costs one hint, not a failure
        return None
    default = nsmap.get(None)
    return default if isinstance(default, str) else None
