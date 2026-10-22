"""Value domain model (design doc 01 §3): the JSON value tree plus the opaque handle.

Two things that are easy to confuse:
- ``JsonValue``: a value that may be exported (export packing accepts nothing else).
- ``Opaque``: a handle (a DOM node, for example) that may flow inside a chain but **must not be
  exported**; export packing reports ``UP2-E2003`` for it.

A third thing flows the same way: **a host object** (a response, a ``udf`` result). It is not
``Opaque`` (the kernel does not own it), but it is no more exportable — it may be an input, an
argument or an answer, and a **step product must still be JSON** (design doc 03 §3.3).
"""

from __future__ import annotations

import json
from typing import Final


class Opaque:
    """Marker base class for non-serializable values (DOM nodes, for example).

    Export packing rejects it.
    """

    __slots__ = ()


type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type Value = JsonValue | Opaque


_PREVIEW_LIMIT: Final = 200

# Exact type -> name in the value domain vocabulary (a table lookup instead of a long isinstance
# chain: faster, and it does not inflate complexity). bool must be tested before int -- but an
# exact-type lookup naturally avoids the "bool is a subclass of int" problem.
_EXACT_TYPE_NAMES: Final[dict[type, str]] = {
    type(None): "null",
    bool: "bool",
    str: "str",
    int: "int",
    float: "float",
    list: "list",
    dict: "dict",
}


def type_name(value: object) -> str:
    """Diagnostic type name (closer to the value domain than ``type(value).__name__``).

    A host object (a response, a ``udf`` result) keeps **its own class name**: that name is the
    only stable fact the kernel has about it, and diagnostics must name it.
    """
    exact = _EXACT_TYPE_NAMES.get(type(value))
    if exact is not None:
        return exact
    if isinstance(value, Opaque):
        return "opaque"
    return type(value).__name__


def is_opaque(value: object) -> bool:
    """Whether this is a handle that cannot be exported."""
    return isinstance(value, Opaque)


def is_json_value(value: object) -> bool:
    """Whether this is an exportable JSON value (recursive; ``dict`` keys must be ``str``)."""
    if value is None or isinstance(value, (str, bool, int, float)):
        return True
    if isinstance(value, list):
        return all(is_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and is_json_value(item) for key, item in value.items())
    return False


def text_of(value: object) -> str:
    """The value's **whole** display text: its JSON text, or a rendering of what is not JSON.

    A **host object** is rendered as its type name plus ``repr``: the kernel cannot render it as
    JSON, and the class name is what tells the reader which host library it came from. This is the
    one rendering ``preview`` truncates and the trace measures as a value's ``size`` (`06` §5.1).
    """
    if isinstance(value, Opaque):
        return f"<opaque {type(value).__name__}>"
    if value is not None and not isinstance(value, (str, bool, int, float, list, dict)):
        return f"{type_name(value)} {value!r}"
    try:
        return json.dumps(value, ensure_ascii=False, default=repr)
    except (TypeError, ValueError):  # pragma: no cover - default=repr already covers it
        return repr(value)


def preview(value: object, limit: int = _PREVIEW_LIMIT) -> str:
    """Short display for diagnostics and traces (not used in business logic)."""
    return truncate(text_of(value), limit)


def truncate(text: str, limit: int = _PREVIEW_LIMIT) -> str:
    """Cut display text to ``limit`` characters; the marker says how much was dropped.

    The marker is **ASCII-only**, because previews and trace events are printed to consoles of every
    encoding. A caller that already rendered the text (the trace measures its length too, `06` §5.1)
    calls this directly instead of rendering the value twice.
    """
    if len(text) > limit:
        return text[:limit] + f"...(+{len(text) - limit})"
    return text
