"""Export packing (design doc 01 §6): the single implementation point of N5.

N5 says "only one function can produce the final product at the export". L1 does two things, but
both must happen in **exactly one place**:
1. reject ``Opaque`` and every non-JSON value (``UP2-E2003``);
2. return the value unchanged once it passes (schema validation belongs to L2).
"""

from __future__ import annotations

from typing import Any

from .errors import Failed, Ok, Outcome
from .values import is_json_value, is_opaque, preview, type_name

_SERIALIZE_FIX = "first turn the node into text via text / html / outer / @<attribute>, then export"


def pack(value: Any, /, *, pointer: str = "") -> Outcome:
    """Pack the chain product; every value that cannot be exported turns into ``Failed``."""
    if is_opaque(value):
        return Failed(
            code="UP2-E2003",
            reason=f"export contains the node handle {type(value).__name__}",
            fix=_SERIALIZE_FIX,
        )
    if not is_json_value(value):
        return Failed(
            code="UP2-E2003",
            reason=f"export contains a value that cannot be serialized: {type_name(value)} "
            f"({preview(value, 80)})",
            fix="only str / int / float / bool / null / list / dict may be exported",
        )
    return Ok(value)
