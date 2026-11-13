"""Read the invariant ids a design note declares, so a test can prove each one is executed.

The kernel invariants live in `01` §1.1 as a Markdown table (`| I3 | … |`), and the numbered
properties `N1`–`N8` live in prose. Both are read here as text — this module never touches the
filesystem: the caller passes the note's content in (invariant I1, `01` §1.1).

**Why this exists.** A design note and the engine drifted apart exactly once, and it was enough:
`type` was documented as a chain-tail JSON validator, every operator's own tests agreed with the
sentence, and the whole gate set stayed green while the engine violated the rule that crosses
operators. A note is only a claim; something has to execute it.
"""

from __future__ import annotations

import re
from typing import Final

_TABLE_ROW: Final = re.compile(r"^\|\s*(I\d+)\s*\|", re.MULTILINE)
_PROSE_ID: Final = re.compile(r"\b(N[1-9])\b")


def parse_declared(text: str) -> set[str]:
    """The invariant ids ``text`` declares: every ``| I<n> |`` row plus every ``N<n>`` mention.

    Only ids the note actually names are reported, so a note that drops an invariant makes the
    coverage audit flag the case that still references it.
    """
    return set(_TABLE_ROW.findall(text)) | set(_PROSE_ID.findall(text))


__all__ = ["parse_declared"]
