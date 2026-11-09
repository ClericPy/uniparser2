"""Export packing (design doc 01 §6): the single implementation point of N5.

N5 says "only one function can produce the final product at the export". L1 does two things, but
both must happen in **exactly one place**:
1. reject ``Opaque`` and every non-JSON value (``UP2-E2003``);
2. return the value unchanged once it passes (schema validation belongs to L2).

The same module owns the **structural comparison** the snapshot regression uses (`04` §7-S5,
`05` §4.2): a snapshot is an external behavioral contract, so a difference between a recorded
product and a fresh one is reported as a **JSON Pointer difference** (pointer + expected + actual),
never as a text diff.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .errors import Failed, Ok, Outcome
from .values import is_json_value, is_opaque, preview, type_name

_SERIALIZE_FIX = "first turn the node into text via text / html / outer / @<attribute>, then export"
_PREVIEW_LIMIT: int = 120
"""How much of one value a difference shows; a product can be megabytes long."""


@dataclass(frozen=True, slots=True)
class ProductDifference:
    """One structural difference between two products (`04` §7-S5).

    ``pointer`` is the JSON Pointer of the value that differs, so a failure is readable without a
    text diff: ``/2/title`` is the third item's ``title`` field.
    """

    pointer: str
    expected: Any
    actual: Any = None
    reason: str = "values differ"

    def to_dict(self) -> dict[str, Any]:
        """The difference as JSON data (``up2 test --json``)."""
        return {
            "pointer": self.pointer,
            "reason": self.reason,
            "expected": preview(self.expected),
            "actual": preview(self.actual),
        }


def compare_products(
    expected: Any, actual: Any, /, *, pointer: str = ""
) -> list[ProductDifference]:
    """Every structural difference between an expected and an actual product, in pointer order.

    The comparison is **structural**, not textual: two products are equal when they are the same
    JSON value (a ``dict`` compares its keys, a ``list`` its positions), and a difference names the
    JSON Pointer rather than printing both documents. ``_``-prefixed keys are ordinary keys here --
    the snapshot is the exit product, where no local survives.
    """
    return list(_diff(expected, actual, pointer))


def _diff(expected: Any, actual: Any, pointer: str) -> list[ProductDifference]:
    if isinstance(expected, Mapping):
        return _diff_mapping(expected, actual, pointer)
    if isinstance(expected, Sequence) and not isinstance(expected, (str, bytes)):
        return _diff_sequence(expected, actual, pointer)
    if type(expected) is not type(actual) or expected != actual:
        return [
            ProductDifference(
                pointer=pointer,
                expected=expected,
                actual=actual,
                reason=_value_reason(expected, actual),
            )
        ]
    return []


def _value_reason(expected: Any, actual: Any) -> str:
    """Why two scalar values differ: a type change is named, a value change is not."""
    if type(expected) is not type(actual):
        return f"expected {type_name(expected)}, got {type_name(actual)}"
    return "values differ"


def _diff_mapping(
    expected: Mapping[str, Any], actual: Any, pointer: str
) -> list[ProductDifference]:
    """A mapping compares key by key: a missing key is ``key absent``, an extra one is ``not``."""
    if not isinstance(actual, Mapping):
        return [_type_difference(pointer, expected, actual)]
    differences: list[ProductDifference] = []
    for key, item in expected.items():
        if key in actual:
            differences.extend(_diff(item, actual[key], f"{pointer}/{key}"))
            continue
        differences.append(
            ProductDifference(pointer=f"{pointer}/{key}", expected=item, reason="key absent")
        )
    for key in actual:
        if key not in expected:
            differences.append(
                ProductDifference(
                    pointer=f"{pointer}/{key}",
                    expected=None,
                    actual=actual[key],
                    reason="not expected",
                )
            )
    return differences


def _diff_sequence(expected: Sequence[Any], actual: Any, pointer: str) -> list[ProductDifference]:
    """A list compares position by position and reports both tails (`04` §7-S5)."""
    if not isinstance(actual, Sequence) or isinstance(actual, (str, bytes)):
        return [_type_difference(pointer, expected, actual)]
    differences: list[ProductDifference] = []
    for position, item in enumerate(expected):
        where = f"{pointer}/{position}"
        if position >= len(actual):
            differences.append(
                ProductDifference(pointer=where, expected=item, reason="item absent")
            )
            continue
        differences.extend(_diff(item, actual[position], where))
    for position in range(len(expected), len(actual)):
        differences.append(
            ProductDifference(
                pointer=f"{pointer}/{position}",
                expected=None,
                actual=actual[position],
                reason="extra item",
            )
        )
    return differences


def _type_difference(pointer: str, expected: Any, actual: Any) -> ProductDifference:
    return ProductDifference(
        pointer=pointer,
        expected=expected,
        actual=actual,
        reason=f"expected {type_name(expected)}, got {type_name(actual)}",
    )


def render_difference(difference: ProductDifference) -> str:
    """One difference as a readable line: the pointer plus the two previews."""
    return (
        f"{difference.pointer} expect {preview(difference.expected, _PREVIEW_LIMIT)} "
        f"got {preview(difference.actual, _PREVIEW_LIMIT)} ({difference.reason})"
    )


def _datetime_export(value: Any) -> Failed:
    """A datetime is internal: the fix names the operator that renders it (design D14)."""
    return Failed(
        code="UP2-E2003",
        reason=f"export contains a datetime ({preview(value, 80)})",
        fix='a datetime is an internal value: render it first with ["py","strftime","%Y-%m-%d '
        '%H:%M:%S"]',
    )


def _contains_datetime(value: Any) -> bool:
    """Whether a product carries a datetime anywhere inside it (only asked after a pack failure)."""
    if isinstance(value, datetime):
        return True
    if isinstance(value, Mapping):
        return any(_contains_datetime(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_datetime(item) for item in value)
    return False


def pack(value: Any, /, *, pointer: str = "") -> Outcome:
    """Pack the chain product; every value that cannot be exported turns into ``Failed``."""
    if is_opaque(value):
        return Failed(
            code="UP2-E2003",
            reason=f"export contains the node handle {type(value).__name__}",
            fix=_SERIALIZE_FIX,
        )
    if isinstance(value, datetime):
        return _datetime_export(value)
    if not is_json_value(value):
        if _contains_datetime(value):
            return _datetime_export(value)
        return Failed(
            code="UP2-E2003",
            reason=f"export contains a value that cannot be serialized: {type_name(value)} "
            f"({preview(value, 80)})",
            fix="only str / int / float / bool / null / list / dict may be exported, "
            "and a float must be finite (JSON has no Infinity / NaN)",
        )
    return Ok(value)
