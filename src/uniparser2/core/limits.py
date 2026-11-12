"""Resource limits (design doc 01 §9).

Chain data **must not override** these constants, otherwise an LLM could unlock itself.

Only the constants the current layers really use are declared here; more are added as their layer
lands.

Known gap (confirmed by measurement, see design doc 02 §6.3): Python 3.14's ``re`` has **no**
``timeout`` parameter (``re.search`` is signed ``(pattern, string, flags=0)``), so there is **no
regex timeout fallback at runtime**. ReDoS defense has two lines: the static nested-quantifier check
at compile time (``UP2-E1013``) plus the input size limit below (``UP2-E2013``, checked at the
evaluator entry). This is a deliberate tradeoff, not an oversight.
"""

from __future__ import annotations

from typing import Final

MAX_STEPS_PER_FIELD: Final = 32
"""The stage limit per field (checked at compile time; exceeding it is ``UP2-E1012``)."""

MAX_TEXT_BYTES: Final = 16 * 1024 * 1024
"""Byte cap on an accepted input text (``UP2-E2013``), checked before any operator sees it.

The cap is on the UTF-8 bytes of a ``str`` input; the evaluator refuses a value that is over it at
its entry, so a huge document never reaches a parser or a regex. It is one of the two ReDoS
defenses (the other is the compile-time nested-quantifier check).
"""

MAX_EACH_DEPTH: Final = 3
"""How deeply ``each`` stages may nest (checked at compile time; exceeding it is ``UP2-E1012``)."""

MAX_EACH_ITER: Final = 10_000
"""How many elements one ``each`` stage may iterate (``UP2-E2012``, checked before it evaluates)."""

MAX_FIELDS_PER_MAP: Final = 256
"""How many fields one field map may declare (compile time; exceeding it is ``UP2-E1012``)."""

MAX_STORY_NODES: Final = 64
"""How many nodes one story bundle may declare (compile time; exceeding it is ``UP2-E1012``)."""

MAX_MATERIALIZE_BYTES: Final = 64 * 1024 * 1024
"""Cap on one run's materialization cache, accounted in **materialized** bytes (`03` §6).

The bound is **soft for a single artifact**: an artifact larger than the cap is retained while it is
in use, so "one document, one parse" holds and the worst case is the cap plus that one artifact.
"""

MAX_MATERIALIZE_ITEMS: Final = 8
"""How many materialized artifacts one run keeps (`03` §6), so many small documents cannot fill the
byte cap with hundreds of tiny trees."""
