"""Value domain model (design doc 01 §3): the JSON value tree plus the opaque handle.

Two things that are easy to confuse:
- ``JsonValue``: a value that may be exported (export packing accepts nothing else).
- ``Opaque``: a handle (a DOM node, for example) that may flow inside a chain but **must not be
  exported**; export packing reports ``UP2-E2003`` for it.
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


class MissingInput:
    """The sentinel for "the previous stage is missing".

    It is passed only to actions that declare ``ActionSpec.accepts_missing`` (``py.default``, for
    example); every other operator never sees it, because missing short-circuits during evaluation.
    """

    __slots__ = ()

    def __repr__(self) -> str:
        return "<MISSING>"


MISSING: Final = MissingInput()
"""The stage-missing sentinel (a singleton)."""

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
    """Diagnostic type name (closer to the value domain than ``type(value).__name__``)."""
    if value is MISSING:
        return "missing"
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


def preview(value: object, limit: int = _PREVIEW_LIMIT) -> str:
    """Short display for diagnostics and traces (not used in business logic)."""
    if value is MISSING:
        return "<MISSING>"
    if isinstance(value, Opaque):
        return f"<opaque {type(value).__name__}>"
    try:
        text = json.dumps(value, ensure_ascii=False, default=repr)
    except (TypeError, ValueError):  # pragma: no cover - default=repr already covers it
        text = repr(value)
    if len(text) > limit:
        # ASCII-only marker: previews are printed to consoles of every encoding.
        return text[:limit] + f"...(+{len(text) - limit})"
    return text
