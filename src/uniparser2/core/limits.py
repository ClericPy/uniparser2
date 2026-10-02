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

MAX_EACH_DEPTH: Final = 3
"""How deeply ``each`` stages may nest (checked at compile time; exceeding it is ``UP2-E1012``)."""

MAX_EACH_ITER: Final = 10_000
"""How many elements one ``each`` stage may iterate (``UP2-E2012``, checked before it evaluates)."""

MAX_FIELDS_PER_MAP: Final = 256
"""How many fields one field map may declare (compile time; exceeding it is ``UP2-E1012``)."""

MAX_STORY_STEPS: Final = 64
"""How many steps one story bundle may declare (compile time; exceeding it is ``UP2-E1012``)."""
