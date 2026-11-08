"""The graph fingerprint (design doc 04 §3).

``blake2s`` at ``digest_size=16`` over the **canonicalised graph only**. The canonical form is
sorted keys, no whitespace and no ASCII escaping, so key order and formatting are irrelevant and
Chinese text survives; ``status``, ``source`` and the timestamps never enter the fingerprint,
because a status change must not produce an audit row saying "the chain changed" (`04` §3).

The fingerprint is the no-op decision of ``publish``: the same graph writes no audit row.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence

from uniparser2.core.values import dumps_json

CANONICAL_SEPARATORS: tuple[str, str] = (",", ":")
DIGEST_SIZE = 16


def canonical_graph(graph: Mapping[str, object] | Sequence[object]) -> str:
    """The canonical JSON text a fingerprint is taken over (`04` §3).

    Strict on purpose: the fingerprint runs before a store writes anything, so a graph that JSON
    cannot express is refused here -- once, for every store implementation (`04` §5 step 2).
    """
    return dumps_json(
        graph,
        sort_keys=True,
        separators=CANONICAL_SEPARATORS,
        subject="the graph",
    )


def graph_hash(graph: Mapping[str, object] | Sequence[object]) -> str:
    """32 hex characters identifying a graph's content (`04` §3)."""
    blob = canonical_graph(graph).encode("utf-8")
    return hashlib.blake2s(blob, digest_size=DIGEST_SIZE).hexdigest()
