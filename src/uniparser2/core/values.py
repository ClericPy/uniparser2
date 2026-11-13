"""Value domain model (design doc 01 §3): the JSON value tree plus the opaque handle.

Two things that are easy to confuse:
- ``JsonValue``: a value inside the JSON domain (what the ``code`` sandbox and every text boundary
  accept).
- ``Opaque``: a handle (a DOM node, for example) that may flow inside a chain and out of the run
  unchanged; only the ``code`` sandbox refuses it (``UP2-E2009``).

A third thing flows the same way: **a host object** (a response, a ``udf`` result). It is not
``Opaque`` (the kernel does not own it), and it may be an input, an argument, or the run's product,
answered exactly as produced (design doc `01` §6).
"""

from __future__ import annotations

import json
import math
from typing import Any, Final

from . import limits
from .errors import Up2Error, diag


class Opaque:
    """Marker base class for non-serializable values (DOM nodes, for example).

    Only the ``code`` sandbox refuses it (``UP2-E2009``); the run hands it back as produced.
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
    """Whether this is a handle the JSON domain cannot render as data."""
    return isinstance(value, Opaque)


def is_json_value(value: object) -> bool:
    """Whether this value is inside the JSON domain (recursive; ``dict`` keys must be ``str``).

    A float must be **finite**: JSON has no ``Infinity`` / ``NaN``, so a product carrying one would
    leave the run as text no strict parser accepts. The computation may still produce one — only the
    boundary refuses it.
    """
    if isinstance(value, float):
        return math.isfinite(value)
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, list):
        return all(is_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and is_json_value(item) for key, item in value.items())
    return False


def text_too_large(value: object) -> bool:
    """Whether a text input is over ``limits.MAX_TEXT_BYTES`` (``UP2-E2013``).

    The cap is on UTF-8 **bytes**. ``len(value) * 4`` is an upper bound on the encoding of a Python
    ``str`` (a code point takes at most four bytes), so the common small value never encodes; a
    value that could be over is encoded once for the exact answer.
    """
    if not isinstance(value, str):
        return False
    cap = limits.MAX_TEXT_BYTES
    if len(value) * 4 <= cap:
        return False
    return len(value.encode("utf-8")) > cap


NON_JSON_FIX: Final = (
    "write JSON values only: a float must be finite, since JSON has no Infinity / NaN"
)
"""The one fix line for "this cannot be JSON", shared by every text boundary."""

_SYNTAX_FIX: Final = (
    "fix the JSON syntax: keys and strings take double quotes, and there is no trailing comma"
)


def dumps_json(
    value: object,
    *,
    indent: int | None = None,
    sort_keys: bool = False,
    separators: tuple[str, str] | None = None,
    subject: str = "the value",
) -> str:
    """Write a value as **strict** JSON text (``allow_nan=False``, ``ensure_ascii=False``).

    ``json.dumps`` would otherwise write ``Infinity`` / ``NaN``, which JSON does not have, and a
    value outside the domain raises ``TypeError``. Both are ``UP2-E1004``: what a text boundary
    writes must be what it would accept back. ``subject`` is the noun the diagnostic names.
    """
    if not _dict_keys_are_strings(value):
        raise Up2Error(
            diag(
                "UP2-E1004",
                f"{subject} contains an object key that is not a string",
                fix='JSON object keys are strings: write {"1": …} rather than {1: …}',
            )
        )
    try:
        return json.dumps(
            value,
            indent=indent,
            sort_keys=sort_keys,
            separators=separators,
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise Up2Error(
            diag("UP2-E1004", f"{subject} cannot be written as JSON: {exc}", fix=NON_JSON_FIX)
        ) from exc


def _dict_keys_are_strings(value: object) -> bool:
    """Every object key is a string, recursively.

    ``json.dumps`` **coerces** an int key to ``"1"`` instead of raising, which would change the
    value silently; the writer refuses it instead. Tuples are accepted: ``json.dumps`` writes them
    as arrays, which is the JSON value they stand for.
    """
    if isinstance(value, dict):
        return all(
            isinstance(key, str) and _dict_keys_are_strings(item) for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return all(_dict_keys_are_strings(item) for item in value)
    return True


def loads_json(text: str | bytes, *, subject: str = "the text") -> Any:
    """Read **strict** JSON text: a non-JSON constant or a syntax error is ``UP2-E1004``.

    Python's decoder accepts ``Infinity`` / ``NaN`` and raises its own ``JSONDecodeError``; the
    package's contract is one coded diagnostic for every kind of bad chain, so both are converted
    here. ``subject`` is the noun the diagnostic names (a file path, for a stored row).
    """

    def reject(name: str) -> Any:
        raise Up2Error(
            diag("UP2-E1004", f"{subject} carries the non-JSON constant {name}", fix=NON_JSON_FIX)
        )

    try:
        return json.loads(text, parse_constant=reject)
    except json.JSONDecodeError as exc:
        raise Up2Error(
            diag("UP2-E1004", f"{subject} is not valid JSON: {exc}", fix=_SYNTAX_FIX)
        ) from exc


def text_of(value: object) -> str:
    """The value's **whole** display text: its JSON text, or a rendering of what is not JSON.

    A **host object** is rendered as its type name plus ``repr``: the kernel cannot render it as
    JSON, and the class name is what tells the reader which host library it came from. This is the
    one rendering ``preview`` truncates and the trace measures as a value's ``size`` (`06` §5.1).

    A container with a non-string key is rendered with ``repr`` instead of JSON text: ``json.dumps``
    would **coerce** the key (``{1: "x"}`` becomes ``{"1": "x"}``), and a diagnostic that shows a
    value looking valid while the JSON writer or the sandbox refuses it is worse than no preview.
    """
    if isinstance(value, Opaque):
        return f"<opaque {type(value).__name__}>"
    if value is not None and not isinstance(value, (str, bool, int, float, list, dict)):
        return f"{type_name(value)} {value!r}"
    if not _dict_keys_are_strings(value):
        return repr(value)
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
