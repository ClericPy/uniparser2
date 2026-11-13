"""The **structural comparison** the snapshot regression uses (`04` §7-S5, `05` §4.2).

A snapshot is an external behavioral contract, so a difference between a recorded product and a
fresh one is reported as a **JSON Pointer difference** (pointer + expected + actual), never as a
text diff.

**There is no export packing.** The engine answers whatever the run produced, as it produced it:
it does not check whether a value is JSON, does not reject a handle, and does not substitute a
friendlier error for one the host could recognize itself. A product the host cannot serialize is
the host's report to make -- the engine's job is to be predictable about what it hands over, not to
guess what the host will do with it (`AGENTS.md`, "Determinism: what you see is what you get").
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .values import preview, type_name

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
