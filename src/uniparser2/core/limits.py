"""Resource limits (design doc 01 §9).

Chain data **must not override** these constants, otherwise an LLM could unlock itself.

Only the constants the current layer really uses are declared here; more are added as their layer
lands (L1 only needs the per-field stage limit).

Known gap (confirmed by measurement, see design doc 02 §6.3): Python 3.14's ``re`` has **no**
``timeout`` parameter (``re.search`` is signed ``(pattern, string, flags=0)``), so there is **no
regex timeout fallback at runtime**. ReDoS defense has only two lines: the static nested-quantifier
check at compile time (``UP2-E1013``) plus the input size limit (``MAX_TEXT_BYTES`` in L2). This is
a deliberate tradeoff, not an oversight.
"""

from __future__ import annotations

from typing import Final

MAX_STEPS_PER_FIELD: Final = 32
"""The stage limit per field (checked at compile time; exceeding it is ``UP2-E1012``)."""
