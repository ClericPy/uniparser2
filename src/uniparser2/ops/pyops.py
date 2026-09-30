"""``py`` operator: 31 allowlist functions (design doc 02 §6.4).

**Slots** (see ``02`` §1): ``["py", function name, parameters]`` — the function name is in slot 2
and its parameters in slot 3.

**A closed set**: anything not in the table raises ``UP2-E1003``. There is no ``eval``/``exec``/
``import`` capability here, so chain data cannot introduce new code (``N6``). Third-party
dependencies are declared per **action** (``html_to_markdown`` needs ``html-to-markdown``); when
missing, that action is unavailable and the install command is reported.

Two groups of functions used to be separate operators and were folded into this table (see D-02-14
in ``02``):

- ``parse_time``: time parsing (the former ``time`` operator). Common machine formats go through a
  stdlib format table with **no required dependency**; ``dateparser`` is used only when ``lang`` is
  given (missing it raises ``UP2-E2008``).
- ``str`` / ``int`` / ``float`` / ``bool`` / ``list`` / ``from_json``: type conversion (the former
  ``cast`` operator) — these are Python built-ins to begin with, and a standalone operator would
  only add another "where does the target type go" convention.
"""

from __future__ import annotations

import base64
import hashlib
import importlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final
from urllib.parse import urljoin as _urljoin
from urllib.parse import urlsplit as _urlsplit

from ..core.ast import Lit, Param
from ..core.errors import Failed, Missing, Ok, Outcome, Up2Error, diag
from ..core.refs import Scope
from ..core.registry import ActionSpec, Call, Kind, Op, ParamSpec, op
from ..core.values import MISSING, is_json_value, type_name

_Fn = Callable[[Any, Mapping[str, Any], Scope], Outcome]

_TAG_PATTERN: Final = re.compile(r"<[^>]*>")
_SPACE_PATTERN: Final = re.compile(r"\s+")
_URL_PARTS: Final = ("scheme", "netloc", "path", "query", "fragment")
_SORT_KEYS: Final = ("str", "int", "float")
_TRUE_TEXT: Final = ("true", "1", "yes")
_MARKDOWN_EXTRA: Final = 'uv add "uniparser2[md]"'

# ---- time parsing (the former time operator) ----
TIME_FORMAT: Final = "%Y-%m-%d %H:%M:%S"
"""The canonical output format (identical to the old v3 ``TIME_OUTPUT``, for easy comparison)."""
_TIME_EXTRA: Final = 'uv add "uniparser2[time]"'
_TIME_FMTS: Final = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d",
    "%Y.%m.%d",
    # The three date patterns below spell their CJK date units as escapes on purpose: the literal
    # characters are part of the pattern the parser must match, and this file stays ASCII.
    "%Y\u5e74%m\u6708%d\u65e5 %H:%M:%S",
    "%Y\u5e74%m\u6708%d\u65e5 %H:%M",
    "%Y\u5e74%m\u6708%d\u65e5",
    "%Y%m%d",
    # The ambiguous ``dd/mm/yyyy`` / ``mm/dd/yyyy`` pair is not listed here: which one is tried
    # first is decided by ``date_order`` (see ``_ambiguous_fmts``), so that a plain date and a
    # date with a time part cannot disagree about the same writing.
    "%d %b %Y",
    "%b %d, %Y",
    # Zone-bearing shapes, so that the two canonical feed timestamps parse with no parameters:
    # RSS 2.0 ``pubDate`` (RFC 822, optionally with the named zones GMT/UTC) and Atom ``updated``
    # (ISO 8601 with Z or a numeric offset). ``%z`` accepts Z as well as +0800/+08:00. The offset is
    # only consumed so that the string parses; the rendered result stays the wall clock in
    # ``TIME_FORMAT`` and is never shifted to UTC.
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%d %H:%M:%S %z",
    "%a, %d %b %Y %H:%M:%S %z",
    "%a, %d %b %Y %H:%M:%S %Z",
)

# ---- type conversion (the former cast operator) ----
_FALSEY_TEXT: Final = frozenset({"", "0", "false", "no", "null", "none"})
_CONTAINER_SEPARATORS: Final = (",", ":")


@dataclass(frozen=True, slots=True)
class _Entry:
    """One allowlist function declaration.

    Table-driven: the declaration and the implementation live in the same entry.
    """

    name: str
    summary: str
    fn: _Fn
    params: tuple[ParamSpec, ...] = ()
    requires: tuple[str, ...] = ()
    accepts_missing: bool = False


def _text(value: Any, who: str) -> str | Failed:
    if isinstance(value, str):
        return value
    return Failed(
        code="UP2-E2002",
        reason=f"py.{who} needs a str, got {type_name(value)}",
        fix="turn the upstream value into text with py.strip_tags / py.getitem / py.get first",
    )


def _items(value: Any, who: str) -> list[Any] | Failed:
    if isinstance(value, list):
        return value
    return Failed(
        code="UP2-E2002",
        reason=f"py.{who} needs a list, got {type_name(value)}",
        fix='cut out a list first with ["py","split",","] / ["css","nodes",S], or take the list '
        'apart with ["each",{...}]',
    )


def _int_param(params: Mapping[str, Any], name: str) -> int:
    raw = params.get(name)
    if isinstance(raw, bool) or raw is None:
        raise ValueError(f"parameter {name} must be an integer")
    return int(raw)


def _py_strip(value: Any, params: Mapping[str, Any], scope: Scope) -> Outcome:
    text = _text(value, "strip")
    return text if isinstance(text, Failed) else Ok(text.strip())


def _py_strip_tags(value: Any, params: Mapping[str, Any], scope: Scope) -> Outcome:
    text = _text(value, "strip_tags")
    return text if isinstance(text, Failed) else Ok(_TAG_PATTERN.sub("", text))


def _py_normalize_space(value: Any, params: Mapping[str, Any], scope: Scope) -> Outcome:
    text = _text(value, "normalize_space")
    return text if isinstance(text, Failed) else Ok(_SPACE_PATTERN.sub(" ", text).strip())


def _py_replace(value: Any, params: Mapping[str, Any], scope: Scope) -> Outcome:
    text = _text(value, "replace")
    if isinstance(text, Failed):
        return text
    old, new = params["old"], params["new"]
    if not isinstance(old, str) or not isinstance(new, str):
        return Failed(code="UP2-E2002", reason="old/new of replace must be strings")
    return Ok(text.replace(old, new))


def _py_split(value: Any, params: Mapping[str, Any], scope: Scope) -> Outcome:
    text = _text(value, "split")
    if isinstance(text, Failed):
        return text
    sep = params["sep"]
    if not isinstance(sep, str):
        return Failed(code="UP2-E2002", reason="the separator of split must be a string")
    raw_max = params.get("maxsplit")
    try:
        if raw_max is None or raw_max == "":
            return Ok(text.split(sep))
        return Ok(text.split(sep, _int_param(params, "maxsplit")))
    except ValueError as exc:
        return Failed(
            code="UP2-E2005",
            reason=f"split failed: {exc}",
            fix="check the separator and maxsplit",
        )


def _py_join(value: Any, params: Mapping[str, Any], scope: Scope) -> Outcome:
    items = _items(value, "join")
    if isinstance(items, Failed):
        return items
    sep = params["sep"]
    if not all(isinstance(item, str) for item in items):
        return Failed(code="UP2-E2002", reason="every element of join must be a string")
    return Ok(str(sep).join(items))


def _py_upper(value: Any, params: Mapping[str, Any], scope: Scope) -> Outcome:
    text = _text(value, "upper")
    return text if isinstance(text, Failed) else Ok(text.upper())


def _py_lower(value: Any, params: Mapping[str, Any], scope: Scope) -> Outcome:
    text = _text(value, "lower")
    return text if isinstance(text, Failed) else Ok(text.lower())


def _parse_slice_spec(spec: str) -> slice:
    parts = spec.split(":")
    if len(parts) > 3:
        raise ValueError(f"invalid slice notation {spec!r}")
    numbers = [None if part.strip() == "" else int(part) for part in parts]
    return slice(*numbers)


def _py_slice(value: Any, params: Mapping[str, Any], scope: Scope) -> Outcome:
    spec = params["spec"]
    if not isinstance(spec, str):
        return Failed(code="UP2-E2002", reason="the spec of slice must be a string")
    if not isinstance(value, (str, list)):
        return Failed(code="UP2-E2002", reason=f"slice does not support {type_name(value)}")
    try:
        return Ok(value[_parse_slice_spec(spec)])
    except ValueError as exc:
        return Failed(code="UP2-E2005", reason=f"slice failed: {exc}", fix='write ":20" / "1:5"')


def _py_getitem(value: Any, params: Mapping[str, Any], scope: Scope) -> Outcome:
    items = _items(value, "getitem")
    if isinstance(items, Failed):
        return items
    try:
        index = _int_param(params, "index")
    except ValueError as exc:
        return Failed(code="UP2-E2002", reason=f"invalid index for getitem: {exc}")
    if not -len(items) <= index < len(items):
        return Missing(
            reason=f"the list has only {len(items)} items, so index {index} is unavailable"
        )
    return Ok(items[index])


def _py_get(value: Any, params: Mapping[str, Any], scope: Scope) -> Outcome:
    if not isinstance(value, Mapping):
        return Failed(code="UP2-E2002", reason=f"get needs a dict, got {type_name(value)}")
    key = params["key"]
    if isinstance(key, (list, dict)):
        return Failed(code="UP2-E2002", reason=f"the key of get is unhashable: {type_name(key)}")
    if key not in value:
        return Missing(reason=f"the dict has no key {key!r}")
    return Ok(value[key])


def _py_len(value: Any, params: Mapping[str, Any], scope: Scope) -> Outcome:
    if isinstance(value, (str, list, dict)):
        return Ok(len(value))
    return Failed(code="UP2-E2002", reason=f"len does not support {type_name(value)}")


def _py_first(value: Any, params: Mapping[str, Any], scope: Scope) -> Outcome:
    items = _items(value, "first")
    if isinstance(items, Failed):
        return items
    return Missing(reason="the list is empty") if not items else Ok(items[0])


def _py_last(value: Any, params: Mapping[str, Any], scope: Scope) -> Outcome:
    items = _items(value, "last")
    if isinstance(items, Failed):
        return items
    return Missing(reason="the list is empty") if not items else Ok(items[-1])


def _py_flatten(value: Any, params: Mapping[str, Any], scope: Scope) -> Outcome:
    items = _items(value, "flatten")
    if isinstance(items, Failed):
        return items
    flat: list[Any] = []
    for item in items:
        flat.extend(item if isinstance(item, (list, tuple)) else [item])
    return Ok(flat)


def _sort_key(name: Any) -> Callable[[Any], Any]:
    if name in (None, "", "str"):
        return str
    if name == "int":
        return int
    if name == "float":
        return float
    raise ValueError(f"the key of sort must be one of {_SORT_KEYS}, got {name!r}")


def _py_sort(value: Any, params: Mapping[str, Any], scope: Scope) -> Outcome:
    items = _items(value, "sort")
    if isinstance(items, Failed):
        return items
    try:
        key = _sort_key(params.get("key"))
        return Ok(sorted(items, key=key, reverse=_truthy(params.get("reverse"))))
    except (ValueError, TypeError) as exc:
        return Failed(
            code="UP2-E2005",
            reason=f"sort failed: {exc}",
            fix="check the element types and the key",
        )


def _truthy(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in _TRUE_TEXT


def _py_uniq(value: Any, params: Mapping[str, Any], scope: Scope) -> Outcome:
    items = _items(value, "uniq")
    if isinstance(items, Failed):
        return items
    seen: list[Any] = []
    for item in items:
        if isinstance(item, (list, dict)):
            return Failed(code="UP2-E2002", reason="uniq does not support list/dict elements")
        if item not in seen:
            seen.append(item)
    return Ok(seen)


def _py_urljoin(value: Any, params: Mapping[str, Any], scope: Scope) -> Outcome:
    text = _text(value, "urljoin")
    if isinstance(text, Failed):
        return text
    base = params.get("base")
    if not isinstance(base, str):
        return Failed(code="UP2-E2002", reason="the base of urljoin must be a string")
    return Ok(_urljoin(base, text))


def _py_urlsplit(value: Any, params: Mapping[str, Any], scope: Scope) -> Outcome:
    text = _text(value, "urlsplit")
    if isinstance(text, Failed):
        return text
    return Ok(getattr(_urlsplit(text), str(params["part"])))


def _py_default(value: Any, params: Mapping[str, Any], scope: Scope) -> Outcome:
    fallback = params.get("value")
    if value is MISSING or value is None or value == "":
        return Ok(fallback)
    return Ok(value)


def _py_b64_encode(value: Any, params: Mapping[str, Any], scope: Scope) -> Outcome:
    text = _text(value, "b64_encode")
    if isinstance(text, Failed):
        return text
    return Ok(base64.b64encode(text.encode("utf-8")).decode("ascii"))


def _py_b64_decode(value: Any, params: Mapping[str, Any], scope: Scope) -> Outcome:
    text = _text(value, "b64_decode")
    if isinstance(text, Failed):
        return text
    try:
        return Ok(base64.b64decode(text, validate=True).decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        return Failed(code="UP2-E2005", reason=f"Base64 decoding failed: {exc}")


def _py_sha256(value: Any, params: Mapping[str, Any], scope: Scope) -> Outcome:
    text = _text(value, "sha256")
    if isinstance(text, Failed):
        return text
    return Ok(hashlib.sha256(text.encode("utf-8")).hexdigest())


def _import_html_to_markdown() -> Callable[..., Any]:
    """Import the optional dependency lazily (the only third-party import, kept substitutable).

    ``importlib.import_module`` is used instead of a static import: when the package is absent a
    static import statement makes each of four type checkers report a missing module once, whereas
    this is an optional dependency that is allowed to be absent — the dynamic import turns
    "present or not" into a runtime fact (``UP2-E2004``).

    Measured contract (``html-to-markdown`` 3.14.3): ``convert(html) -> ConversionResult``, with the
    Markdown text on the result's ``.content``. It has **no** base_url notion, so this function does
    not accept that parameter and relative-link completion is done explicitly by ``py.urljoin`` in
    the chain.
    """
    module = importlib.import_module("html_to_markdown")
    # getattr rather than module.convert: attribute access on ModuleType is not recognized.
    converter: Callable[..., Any] = getattr(module, "convert")  # noqa: B009
    return converter


def _py_html_to_markdown(value: Any, params: Mapping[str, Any], scope: Scope) -> Outcome:
    del params, scope
    text = _text(value, "html_to_markdown")
    if isinstance(text, Failed):
        return text
    try:
        convert = _import_html_to_markdown()
    except ImportError as exc:
        return Failed(
            code="UP2-E2004",
            reason=f"html_to_markdown needs html-to-markdown: {exc}",
            fix=f"install the optional dependency: {_MARKDOWN_EXTRA}",
        )
    try:
        content = convert(text).content
    except Exception as exc:  # a third-party conversion failure must become a coded Failed
        return Failed(code="UP2-E2005", reason=f"HTML→Markdown failed: {exc}")
    if not isinstance(content, str):
        return Failed(
            code="UP2-E2005",
            reason=f"the converter returned a non-text result: {type_name(content)}",
            fix="make sure the html-to-markdown version is compatible (.content must be str)",
        )
    return Ok(content)


# ---------------------------------------------------------------- type conversion (former cast)


def _convert(value: Any, who: str, converter: Callable[[Any], Any]) -> Outcome:
    try:
        return Ok(converter(value))
    except (TypeError, ValueError) as exc:
        return Failed(
            code="UP2-E2005",
            reason=f"py.{who} conversion failed: {exc}",
            fix="check the shape of the source value first (py.default can serve as a fallback)",
        )


def _to_str(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, separators=_CONTAINER_SEPARATORS)
    return str(value)


def _to_int(value: Any) -> int:
    if isinstance(value, (bool, int, float)):
        return int(value)
    if isinstance(value, str):
        return int(value.strip())
    raise TypeError(f"{type_name(value)} cannot be converted to int")


def _to_float(value: Any) -> float:
    if isinstance(value, (bool, int, float)):
        return float(value)
    if isinstance(value, str):
        return float(value.strip())
    raise TypeError(f"{type_name(value)} cannot be converted to float")


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in _FALSEY_TEXT
    if isinstance(value, (int, float)):
        return value != 0
    if value is None:
        return False
    if isinstance(value, (list, dict)):
        return len(value) > 0
    raise TypeError(f"{type_name(value)} cannot be converted to bool")


def _to_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        if not isinstance(parsed, list):
            raise TypeError("the string is not a JSON array")
        return parsed
    raise TypeError(f"{type_name(value)} cannot be converted to list")


def _to_json(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    if is_json_value(value):
        return value
    raise TypeError(f"{type_name(value)} is not a JSON value")


def _py_str(value: Any, params: Mapping[str, Any], scope: Scope) -> Outcome:
    del params, scope
    return _convert(value, "str", _to_str)


def _py_int(value: Any, params: Mapping[str, Any], scope: Scope) -> Outcome:
    del params, scope
    return _convert(value, "int", _to_int)


def _py_float(value: Any, params: Mapping[str, Any], scope: Scope) -> Outcome:
    del params, scope
    return _convert(value, "float", _to_float)


def _py_bool(value: Any, params: Mapping[str, Any], scope: Scope) -> Outcome:
    del params, scope
    return _convert(value, "bool", _to_bool)


def _py_list(value: Any, params: Mapping[str, Any], scope: Scope) -> Outcome:
    del params, scope
    return _convert(value, "list", _to_list)


def _py_from_json(value: Any, params: Mapping[str, Any], scope: Scope) -> Outcome:
    del params, scope
    return _convert(value, "from_json", _to_json)


# ---------------------------------------------------------------- time parsing (former time)


def _import_dateparser() -> Callable[..., Any]:
    """Import the optional enhancement lazily (a dynamic import hides missing modules)."""
    module = importlib.import_module("dateparser")
    parser: Callable[..., Any] = getattr(module, "parse")  # noqa: B009 - ModuleType attribute
    return parser


def _py_parse_time(value: Any, params: Mapping[str, Any], scope: Scope) -> Outcome:
    del scope
    if value is None:
        return Missing(reason="the time value is empty")
    if not isinstance(value, str):
        return Failed(
            code="UP2-E2002",
            reason=f"py.parse_time needs a str input, got {type_name(value)}",
            fix="turn the upstream value into text with py.strip / py.getitem first",
        )
    text = value.strip()
    if not text:
        return Missing(reason="the time text is empty")

    fmt = params.get("format")
    if fmt:
        return _time_with_format(text, str(fmt))
    order = params.get("date_order") or _TIME_DATE_ORDER_DEFAULT
    parsed = _time_by_table(text, str(order))
    if parsed is not None:
        return Ok(parsed.strftime(TIME_FORMAT))
    return _time_by_language(text, params, order=str(order))


def _time_with_format(text: str, fmt: str) -> Outcome:
    try:
        return Ok(datetime.strptime(text, fmt).strftime(TIME_FORMAT))
    except ValueError as exc:
        return Failed(
            code="UP2-E2007",
            reason=f"parsing {text!r} with format {fmt!r} failed: {exc}",
            fix="check format against the actual layout of the time string",
        )


def _time_by_table(text: str, order: str) -> datetime | None:
    """The built-in shapes, with the ambiguous slash pair tried in the requested order.

    The pair is ordered rather than listed because a plain ``03/04/2026`` and a ``03/04/2026 15:30``
    must not disagree: the table decides the first, the engine the second, and both are driven by
    the same ``date_order`` value.
    """
    for candidate in (*_TIME_FMTS, *_ambiguous_fmts(order)):
        try:
            return datetime.strptime(text, candidate)
        except ValueError:
            continue
    return None


def _time_by_language(text: str, params: Mapping[str, Any], *, order: str) -> Outcome:
    """The last resort: the optional engine, detecting the language unless ``lang`` restricts it.

    ``lang`` no longer gates the engine (a chain should not have to name a language to read one), it
    only narrows the detection. ``order`` and ``now`` are passed through as engine settings, so an
    ambiguous numeric date and the base clock of a relative expression are the chain's decisions
    rather than the library's. Without the extra the outcome is a coded error, never another value.
    """
    try:
        parse = _import_dateparser()
    except ImportError as exc:
        return Failed(
            code="UP2-E2008",
            reason=f"natural-language dates need dateparser: {exc}",
            fix=f"install the optional dependency: {_TIME_EXTRA}",
        )
    lang = params.get("lang")
    settings: dict[str, Any] = {"DATE_ORDER": order}
    now = params.get("now")
    if now:
        base = _parse_canonical(str(now))
        if base is None:
            return Failed(
                code="UP2-E2007",
                reason=f"now must be the canonical time {TIME_FORMAT}, got {now!r}",
                fix='write the canonical shape, for example "2026-01-01 12:00:00"',
            )
        settings["RELATIVE_BASE"] = base
    try:
        parsed = parse(text, languages=[str(lang)] if lang else None, settings=settings or None)
    except Exception as exc:  # a third-party parse failure must become a coded Failed
        return Failed(
            code="UP2-E2007",
            reason=f"dateparser failed to parse: {exc}",
            fix="check the text, or restrict the language with lang",
        )
    if parsed is None:
        return Failed(
            code="UP2-E2007",
            reason=f"nothing could read the time string {text!r}",
            fix=(
                "extract the time fragment with re/py first, or give an explicit layout "
                'such as {"format": "%Y-%m-%d"}'
            ),
        )
    return Ok(parsed.strftime(TIME_FORMAT))


def _check_time_format(params: Mapping[str, Param], *, pointer: str = "") -> None:
    raw = params["format"]
    fmt = raw.value if isinstance(raw, Lit) else raw
    if fmt is None:
        return
    target = pointer or "/2/format"
    if not isinstance(fmt, str) or not fmt:
        raise Up2Error(
            diag(
                "UP2-E1005",
                f"format must be a non-empty string, got {fmt!r}",
                fix='write a strptime format such as "%Y-%m-%d %H:%M:%S"',
                pointer=target,
            )
        )
    try:
        datetime.strptime("", fmt)
    except ValueError as exc:
        # `_strptime` (pure Python, the same on every platform) reports a format it cannot use
        # with a message ending in "in format '<fmt>'": "'Q' is a bad directive in format '%Q'"
        # or "stray % in format '%'". Its other ValueError — "time data '' does not match
        # format ..." — only says the probe text does not fit, not that the format is bad.
        #
        # Probing with `strftime` (what this check did before) is **platform-dependent**: glibc
        # passes an unknown directive through verbatim while the Windows CRT raises, so the same
        # chain compiled on Linux and was rejected on Windows. Asking `strptime` also matches
        # what the operator does at parse time, so a format it accepts is never rejected here.
        if " in format " not in str(exc):
            return
        raise Up2Error(
            diag(
                "UP2-E1005",
                f"invalid strptime format: {exc}",
                fix="fix the directives in format",
                pointer=target,
            )
        ) from exc


_TIME_DATE_ORDER_DEFAULT: Final = "DMY"
"""Day first, which is what the built-in table has always done for a plain ``03/04/2026``."""

_AMBIGUOUS_ORDER: Final[Mapping[str, tuple[str, str]]] = {
    "MDY": ("%m/%d/%Y", "%d/%m/%Y"),
    "DMY": ("%d/%m/%Y", "%m/%d/%Y"),
}
"""The two writings of an ambiguous slash date, in the order the requested policy tries them."""


def _ambiguous_fmts(order: str) -> tuple[str, ...]:
    return _AMBIGUOUS_ORDER.get(order, _AMBIGUOUS_ORDER[_TIME_DATE_ORDER_DEFAULT])


_TIME_DATE_ORDERS: Final = ("MDY", "DMY", "YMD")
"""The numeric orders the engine understands (``settings["DATE_ORDER"]``)."""


def _written(raw: Param | None) -> Any:
    """The value as written in the chain (``Lit``), or the structure behind a reference."""
    return raw.value if isinstance(raw, Lit) else raw


def _check_time_params(params: Mapping[str, Param], *, pointer: str = "") -> None:
    """The compile-time checks of ``py.parse_time``: layout, order, base clock, combination."""
    _check_time_format(params, pointer=f"{pointer}/format")
    fmt = _written(params.get("format"))
    lang = _written(params.get("lang"))
    if fmt and lang:
        raise Up2Error(
            diag(
                "UP2-E1005",
                "format and lang cannot be given together: the explicit format wins, so the "
                "language would never have an effect",
                fix=(
                    'keep one of them — give "format" for an explicit layout, or drop it and let '
                    "the language detection run"
                ),
                pointer=f"{pointer}/lang" if pointer else "/2/lang",
            )
        )
    order = _written(params.get("date_order"))
    if order is not None and order not in _TIME_DATE_ORDERS:
        raise Up2Error(
            diag(
                "UP2-E1005",
                f"date_order must be one of {_TIME_DATE_ORDERS}, got {order!r}",
                fix='write "MDY" (month first), "DMY" (day first) or "YMD"',
                pointer=f"{pointer}/date_order" if pointer else "/2/date_order",
                allowed=_TIME_DATE_ORDERS,
            )
        )
    now = _written(params.get("now"))
    if isinstance(now, str) and now and _parse_canonical(now) is None:
        raise Up2Error(
            diag(
                "UP2-E1005",
                f"now must be the canonical time {TIME_FORMAT}, got {now!r}",
                fix=(
                    'write the canonical shape, for example "2026-01-01 12:00:00", or a '
                    'reference such as "$globals.now"'
                ),
                pointer=f"{pointer}/now" if pointer else "/2/now",
            )
        )


# ---------------------------------------------------------------- time rendering (output side)

_STRFTIME_ALLOWED: Final = frozenset("YymdHMISfjUWwu")
"""The directives whose rendering is locale-free and stable across platforms (design D6)."""

_STRFTIME_REJECTED: Final[Mapping[str, str]] = {
    "a": "the short weekday name is decided by the process locale",
    "A": "the weekday name is decided by the process locale",
    "b": "the short month name is decided by the process locale",
    "B": "the month name is decided by the process locale",
    "p": "the AM/PM marker is decided by the process locale",
    "c": "the locale's date and time representation is decided by the process locale",
    "x": "the locale's date representation is decided by the process locale",
    "X": "the locale's time representation is decided by the process locale",
    "z": "the canonical value carries no zone, so an offset would always render as empty",
    "Z": "the canonical value carries no zone, so a zone name would always render as empty",
    "e": "a platform-specific directive (glibc); it is not available everywhere",
    "k": "a platform-specific directive (glibc); it is not available everywhere",
    "l": "a platform-specific directive (glibc); it is not available everywhere",
    "G": "the ISO year is platform-dependent and needs the ISO week and weekday together",
    "V": "the ISO week is platform-dependent",
    "s": "epoch seconds would have to assume a zone for a zone-less value",
}

_STRFTIME_FIX: Final = (
    'use numeric directives such as "%Y-%m-%d" / "%H:%M:%S", or reshape the pieces with py.slice'
)


def _parse_canonical(text: str) -> datetime | None:
    """Parse the canonical time shape, or report that the text is not one (strictly zero-padded)."""
    try:
        return datetime.strptime(text, TIME_FORMAT)
    except ValueError:
        return None


def _py_strftime(value: Any, params: Mapping[str, Any], scope: Scope) -> Outcome:
    del scope
    if not isinstance(value, str):
        return Failed(
            code="UP2-E2002",
            reason=f"py.strftime needs the canonical time string, got {type_name(value)}",
            fix="produce it first with py.parse_time",
        )
    parsed = _parse_canonical(value)
    if parsed is None:
        return Failed(
            code="UP2-E2007",
            reason=f"{value!r} is not the canonical time shape {TIME_FORMAT}",
            fix="normalise the value first with py.parse_time",
        )
    return Ok(parsed.strftime(str(params["layout"])))


def _layout_directives(layout: str) -> list[str]:
    """Every directive character, with ``""`` for a trailing ``%`` and ``"%"`` for ``%%``."""
    found: list[str] = []
    index = 0
    while index < len(layout):
        if layout[index] != "%":
            index += 1
            continue
        if index + 1 >= len(layout):
            found.append("")
            break
        found.append(layout[index + 1])
        index += 2
    return found


def _check_strftime_layout(params: Mapping[str, Param], *, pointer: str = "") -> None:
    """Reject a layout that cannot render identically on every platform and locale (design D6)."""
    target = pointer or "/2/layout"
    layout = _written(params.get("layout"))
    if not isinstance(layout, str) or not layout:
        raise Up2Error(
            diag(
                "UP2-E1005",
                f"layout must be a non-empty string, got {layout!r}",
                fix=_STRFTIME_FIX,
                pointer=target,
            )
        )
    for directive in _layout_directives(layout):
        if directive == "%":
            continue
        if directive == "":
            raise Up2Error(
                diag(
                    "UP2-E1005",
                    f"layout {layout!r} ends with a stray %",
                    fix='write "%%" for a literal percent sign',
                    pointer=target,
                )
            )
        reason = _STRFTIME_REJECTED.get(directive)
        if reason:
            raise Up2Error(
                diag(
                    "UP2-E1005",
                    f"%{directive} cannot be rendered: {reason}",
                    fix=_STRFTIME_FIX,
                    pointer=target,
                )
            )
        if directive not in _STRFTIME_ALLOWED:
            raise Up2Error(
                diag(
                    "UP2-E1005",
                    f"unknown directive %{directive} in the layout",
                    fix=_STRFTIME_FIX,
                    pointer=target,
                    allowed=tuple(sorted(_STRFTIME_ALLOWED)),
                )
            )


_SCALAR_PARAMS: Final[Mapping[str, Mapping[str, str]]] = {
    "urljoin": {"base": "a string"},
    "slice": {"spec": "a string"},
    "split": {"sep": "a string", "maxsplit": "an integer"},
    "getitem": {"index": "an integer"},
    "get": {"key": "a string"},
    "replace": {"old": "a string", "new": "a string"},
    "strftime": {"layout": "a string"},
}
"""Parameters whose runtime path needs a scalar (design D3 of ``add-parameter-shape-contract``).

A JSON container here is always a mistake: these functions either reject it with ``UP2-E2002`` or
raise inside ``int()``. Parameters that merely coerce their argument (``join.sep``,
``parse_time.lang``) and the any-typed ``default.value`` are deliberately absent — there a container
is a legal value.
"""


def _check_scalar_params(action: str, params: Mapping[str, Param], *, pointer: str = "") -> None:
    """Reject a container where the function's own runtime path requires a scalar."""
    wanted = _SCALAR_PARAMS.get(action)
    if not wanted:
        return
    for name, expected in wanted.items():
        raw = params.get(name)
        # A ``Lit`` holds the value as written; a container written for a ``ref_or_literal``
        # parameter is walked into ``Param`` structures instead; a ``Ref`` is only known at runtime.
        written = raw.value if isinstance(raw, Lit) else raw
        if isinstance(written, (Mapping, list, tuple)):
            raise Up2Error(
                diag(
                    "UP2-E1005",
                    f"parameter {name!r} of py.{action} must be {expected}, "
                    f"got {type_name(written)}",
                    fix=_scalar_fix(action, name),
                    pointer=f"{pointer}/{name}" if pointer else f"/2/{name}",
                )
            )


def _scalar_fix(action: str, name: str) -> str:
    """The accepted writing, derived from how many parameters the action still has to fill."""
    declared = _ENTRIES[action].params
    if len(declared) == 1:
        return f'write the value directly: ["py", "{action}", "…"]'
    names = ", ".join(repr(param.name) for param in declared)
    return f'write the parameters as a named object with {names}, for example {{"{name}": …}}'


_SORT_KEYS_ALLOWED: Final = ("", *_SORT_KEYS)


def _check_sort_key(params: Mapping[str, Param], *, pointer: str = "") -> None:
    """``sort.key`` is an enum, so an unknown value is decidable before the run."""
    raw = params.get("key")
    if not isinstance(raw, Lit):
        return
    key = raw.value
    if key is None or key in _SORT_KEYS_ALLOWED:
        return
    raise Up2Error(
        diag(
            "UP2-E1005",
            f"the key of sort must be one of {_SORT_KEYS_ALLOWED}, got {key!r}",
            fix='write "str", "int" or "float", or drop the parameter',
            pointer=pointer or "/2/key",
            allowed=_SORT_KEYS_ALLOWED,
        )
    )


_TABLE: Final[tuple[_Entry, ...]] = (
    _Entry("strip", "strip leading and trailing whitespace", _py_strip),
    _Entry("strip_tags", "remove HTML tags", _py_strip_tags),
    _Entry(
        "normalize_space",
        "collapse runs of whitespace into a single space",
        _py_normalize_space,
    ),
    _Entry(
        "html_to_markdown",
        "HTML → Markdown (no parameters; complete relative links with py.urljoin)",
        _py_html_to_markdown,
        (),
        ("html_to_markdown",),
    ),
    _Entry(
        "replace",
        "replace all occurrences",
        _py_replace,
        (ParamSpec("old", Kind.LITERAL), ParamSpec("new", Kind.LITERAL)),
    ),
    _Entry(
        "split",
        "split on a separator",
        _py_split,
        (
            ParamSpec("sep", Kind.LITERAL),
            ParamSpec("maxsplit", Kind.LITERAL, required=False, default=None),
        ),
    ),
    _Entry("join", "join a list", _py_join, (ParamSpec("sep", Kind.LITERAL),)),
    _Entry("upper", "convert to uppercase", _py_upper),
    _Entry("lower", "convert to lowercase", _py_lower),
    _Entry("slice", "slice a string or list", _py_slice, (ParamSpec("spec", Kind.LITERAL),)),
    _Entry("getitem", "take a list index", _py_getitem, (ParamSpec("index", Kind.LITERAL),)),
    _Entry("get", "fetch a dict key", _py_get, (ParamSpec("key", Kind.LITERAL),)),
    _Entry("len", "length", _py_len),
    _Entry("first", "take the first element", _py_first),
    _Entry("last", "take the last element", _py_last),
    _Entry("flatten", "flatten one level", _py_flatten),
    _Entry(
        "sort",
        "stable sort",
        _py_sort,
        (
            ParamSpec("key", Kind.LITERAL, required=False, default=None),
            ParamSpec("reverse", Kind.LITERAL, required=False, default=False),
        ),
    ),
    _Entry("uniq", "deduplicate while preserving order", _py_uniq),
    _Entry(
        "urljoin",
        "resolve relative to absolute",
        _py_urljoin,
        (ParamSpec("base", Kind.REF_OR_LITERAL),),
    ),
    _Entry(
        "urlsplit",
        "split a URL into parts",
        _py_urlsplit,
        (ParamSpec("part", Kind.LITERAL),),
    ),
    _Entry(
        "default",
        "fall back when empty/None/missing",
        _py_default,
        (ParamSpec("value", Kind.REF_OR_LITERAL),),
        (),
        True,
    ),
    _Entry("b64_encode", "Base64 encode", _py_b64_encode),
    _Entry("b64_decode", "Base64 decode", _py_b64_decode),
    _Entry("sha256", "hexadecimal digest", _py_sha256),
    _Entry(
        "parse_time",
        "parse a time string into the canonical format %Y-%m-%d %H:%M:%S (explicit format, the "
        "built-in table, then natural-language detection)",
        _py_parse_time,
        (
            ParamSpec("lang", Kind.LITERAL, required=False, default=None),
            ParamSpec("format", Kind.LITERAL, required=False, default=None),
            ParamSpec("date_order", Kind.LITERAL, required=False, default=None),
            ParamSpec("now", Kind.REF_OR_LITERAL, required=False, default=None),
        ),
    ),
    _Entry(
        "strftime",
        "render the canonical time string in another layout (%Y-%m-%d %H:%M:%S → %Y/%m/%d)",
        _py_strftime,
        (ParamSpec("layout", Kind.LITERAL),),
    ),
    _Entry("str", "convert to a string (former cast str)", _py_str),
    _Entry("int", "convert to an integer (former cast int)", _py_int),
    _Entry("float", "convert to a float (former cast float)", _py_float),
    _Entry("bool", "convert to a boolean (former cast bool)", _py_bool),
    _Entry("list", "convert to a list (JSON array text or as-is)", _py_list),
    _Entry("from_json", "JSON text → JSON tree (former cast json)", _py_from_json),
)

_FUNCS: Final[Mapping[str, _Fn]] = {entry.name: entry.fn for entry in _TABLE}
_ENTRIES: Final[Mapping[str, _Entry]] = {entry.name: entry for entry in _TABLE}
_ACTIONS: Final[Mapping[str, ActionSpec]] = {
    entry.name: ActionSpec(
        entry.name,
        entry.summary,
        entry.params,
        entry.requires,
        entry.accepts_missing,
    )
    for entry in _TABLE
}


@op("py", aliases=("python",))
class Py(Op):
    """The allowlist function set (32 functions, closed)."""

    summary = "Python built-in allowlist functions"
    slot_roles = ("function", "params")
    actions = _ACTIONS

    def resolve_action(self, action_text: Any, *, pointer: str = "") -> str:
        if not isinstance(action_text, str) or action_text not in self.actions:
            raise Up2Error(
                diag(
                    "UP2-E1003",
                    f"the py allowlist has no function {action_text!r}",
                    fix="use one of the functions below (run up2 ops --json for the full table)",
                    pointer=pointer,
                    allowed=tuple(sorted(self.actions)),
                )
            )
        return action_text

    def precompile(self, action: str, params: Mapping[str, Param], *, pointer: str = "") -> Any:
        _check_scalar_params(action, params, pointer=pointer)
        if action == "sort":
            _check_sort_key(params, pointer=f"{pointer}/key")
        elif action == "urlsplit":
            _check_url_part(params, pointer=f"{pointer}/part")
        elif action == "parse_time":
            _check_time_params(params, pointer=pointer)
        elif action == "strftime":
            _check_strftime_layout(params, pointer=pointer)
        return None

    def evaluate(self, call: Call) -> Outcome:
        return _FUNCS[call.action](call.value, call.params, call.scope)


def _check_url_part(params: Mapping[str, Param], *, pointer: str = "") -> None:
    raw = params["part"]
    part = raw.value if isinstance(raw, Lit) else raw
    if part not in _URL_PARTS:
        raise Up2Error(
            diag(
                "UP2-E1005",
                f"the part of urlsplit must be one of {_URL_PARTS}, got {part!r}",
                fix="change the part value",
                pointer=pointer or "/2/part",
                allowed=_URL_PARTS,
            )
        )


def functions() -> Sequence[str]:
    """The allowlist function names (conformance, the docs, and the ``code`` sandbox mount)."""
    return tuple(entry.name for entry in _TABLE)


def call_positional(name: str, args: Sequence[Any], scope: Scope) -> Outcome:
    """Call an allowlist function by **positional arguments** (used by the ``code`` sandbox mount).

    The ``normalize_space(obj)`` form is the typical one. The first argument is the value being
    processed and the rest are bound in the order of that function's parameter table. Too few or
    too many arguments, or a nonexistent function, all return ``Failed`` — the sandbox side turns
    it into an exception that the snippet can catch with ``try/except``.
    """
    entry = _ENTRIES.get(name)
    if entry is None:
        return Failed(
            code="UP2-E1003",
            reason=f"the py allowlist has no function {name!r}",
            fix="use a function from the allowlist (run up2 ops --json for the full table)",
        )
    if not args:
        return Failed(
            code="UP2-E2002",
            reason=f"py.{name} needs at least 1 argument (the value being processed)",
            fix=f"pass arguments according to the parameter table of py.{name}",
        )
    value, rest = args[0], args[1:]
    if len(rest) > len(entry.params):
        return Failed(
            code="UP2-E2002",
            reason=f"py.{name} accepts at most {len(entry.params)} arguments, got {len(rest)}",
            fix="drop the extra arguments, or use the parameter-object form",
        )
    params: dict[str, Any] = {spec.name: arg for spec, arg in zip(entry.params, rest, strict=False)}
    missing = [spec.name for spec in entry.params if spec.required and spec.name not in params]
    if missing:
        return Failed(
            code="UP2-E2005",
            reason=f"py.{name} is missing required arguments {missing}",
            fix=f"add them according to the parameter table of py.{name}",
        )
    return entry.fn(value, params, scope)
