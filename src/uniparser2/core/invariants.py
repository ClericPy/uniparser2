"""Read the invariant ids the design notes declare, so a test can prove each one is executed.

The kernel invariants live in `01` §1.1 as a Markdown table (`| I3 | … |`), and the numbered
contracts `N1`–`N8` live in `00` §2's table (`| **N1** | … |`) and in prose. Both are read here as
text — this module never touches the filesystem: the caller passes the notes' content in
(invariant I1, `01` §1.1).

**Why this exists.** A design note and the engine drifted apart exactly once, and it was enough:
`type` was documented as a chain-tail JSON validator, every operator's own tests agreed with the
sentence, and the whole gate set stayed green while the engine violated the rule that crosses
operators. A note is only a claim; something has to execute it.
"""

from __future__ import annotations

import re
from typing import Final

_TABLE_ROW: Final = re.compile(r"^\|\s*\*{0,2}((?:I|N)\d+)\*{0,2}\s*\|", re.MULTILINE)
"""A table row naming one invariant id: `| I3 | …` (001) or `| **N1** | …` (000)."""
_PROSE_ID: Final = re.compile(r"\b((?:I|N)\d+)\b")
"""An id mentioned in prose, where the notes cross-reference each other."""


def parse_declared(text: str) -> set[str]:
    """The invariant ids ``text`` declares: every table row naming one plus every prose mention.

    Only ids a note actually names are reported, so a note that drops an invariant makes the
    coverage audit flag the case that still references it.
    """
    return set(_TABLE_ROW.findall(text)) | set(_PROSE_ID.findall(text))


__all__ = ["parse_declared"]
