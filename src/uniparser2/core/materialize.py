"""The run-scoped materialization cache (design doc `03` §6).

A story does not materialize its input: the operator that consumes a value decides how it becomes
structure (`css` / `css1` -> HTML, `xpath` -> XML, `json` -> JSON text). "One document, one parse"
is then this cache's job rather than an entry point's: it is scoped to **one run**, keyed by the
target format plus the source value, accounted in **materialized bytes**, and bounded by
``MAX_MATERIALIZE_BYTES`` and ``MAX_MATERIALIZE_ITEMS`` with LRU eviction (``core/limits.py``).

Five rules, all of them contracts rather than optimizations:

- **Scope**: it lives with one run and is released with it, so no handle outlives the run that
  produced it and two runs cannot observe each other.
- **Key**: the target format plus the source value -- object identity first, a content hash on a
  miss. Each entry holds a **strong reference to its source**, so an entry's source cannot be
  collected while the entry lives (which is what makes the identity check sound) and an equal but
  distinct string still hits through the digest.
- **Bound**: ``MAX_MATERIALIZE_BYTES`` with LRU eviction, accounted in materialized bytes -- not in
  source-text bytes, because the amplification differs per format (measured: a selectolax DOM is
  ~24x its HTML text, a JSON tree ~2.2-2.7x). ``MAX_MATERIALIZE_ITEMS`` caps the artifact count, so
  a run over many small documents cannot fill the byte cap with hundreds of tiny trees.
- **The cap is soft for the artifact in use**: an artifact larger than the byte cap is still
  retained while it is being materialized, so the worst case is the cap plus that one artifact.
- **No mutation**: materialization is a pure function of the source text, so a hit and a miss are
  observably identical (a test pins that equality), and a cached artifact must not be mutated in
  place -- an operator whose work would change it (pruning an HTML document) works on a copy.

The module is pure data-structure work plus one call: no third-party import, no file read, no IO.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import blake2b
from typing import Any, Final

from .limits import MAX_MATERIALIZE_BYTES, MAX_MATERIALIZE_ITEMS

HTML: Final = "html"
XML: Final = "xml"
JSON: Final = "json"
"""The target formats a consumer materializes (``03`` §6's per-consumer table)."""

_DIGEST_BYTES: Final = 16
"""Digest width for the content fallback: 128 bits keep an accidental collision out of reach."""


@dataclass(slots=True)
class MaterializedArtifact:
    """One cached artifact: what was built, from which source, and what it costs (``03`` §6).

    ``source`` is the entry's strong reference to the text it was built from: it keeps the identity
    fast path sound (the string cannot be collected and its address reused while the entry lives)
    and it lets a lookup compare contents when the caller passes an equal but distinct string.
    """

    format: str
    source: str
    artifact: Any
    size: int
    digest: str


Materialize = Callable[[str], tuple[Any, int]]
"""How a consumer materializes: the source text in, ``(artifact, materialized bytes)`` out."""


class Materializer:
    """One run's cache of materialized artifacts (``03`` §6).

    Recency is an ``OrderedDict``'s insertion order: a read moves its entry to the end, and an
    insertion evicts from the front until both bounds hold -- never evicting the entry it is
    building, which is the "one artifact may exceed the cap while it is in use" rule.
    """

    __slots__ = ("_artifacts", "_bytes", "_max_bytes", "_max_items")

    def __init__(
        self,
        *,
        max_bytes: int = MAX_MATERIALIZE_BYTES,
        max_items: int = MAX_MATERIALIZE_ITEMS,
    ) -> None:
        self._artifacts: OrderedDict[tuple[str, int], MaterializedArtifact] = OrderedDict()
        self._bytes = 0
        self._max_bytes = max_bytes
        self._max_items = max_items

    @property
    def bytes(self) -> int:
        """The materialized bytes this run currently holds (``03`` §6's accounting unit)."""
        return self._bytes

    @property
    def max_bytes(self) -> int:
        """The byte bound in force (``MAX_MATERIALIZE_BYTES`` by default)."""
        return self._max_bytes

    @property
    def max_items(self) -> int:
        """The artifact-count bound in force (``MAX_MATERIALIZE_ITEMS`` by default)."""
        return self._max_items

    def __len__(self) -> int:
        """How many artifacts the run currently holds."""
        return len(self._artifacts)

    def get(self, kind: str, source: str, build: Materialize) -> Any:
        """The artifact for ``(kind, source)``, materializing it on a miss (``03`` §6).

        ``kind`` is the target format. ``build`` answers ``(artifact, materialized bytes)``; it is
        called only on a miss, so a hit costs one hash lookup and nothing else. The key carries the
        format, so the same text materialized as HTML and as XML are two entries.
        """
        key = (kind, hash(source))
        entry = self._find(key, source)
        if entry is not None:
            return entry.artifact
        artifact, size = build(source)
        self._store(kind, key, source, artifact, size)
        return artifact

    def clear(self) -> None:
        """Drop every artifact of this run (the release of ``03`` §6)."""
        self._artifacts.clear()
        self._bytes = 0

    def _find(self, key: tuple[str, int], source: str) -> MaterializedArtifact | None:
        """A hit: identity first, then the content digest on the same bucket (``03`` §6).

        Two things make this sound. The key carries the source's own hash, and the entry is
        accepted only when its source **is** the queried object or its digest matches the queried
        text -- so a hash collision, or an address reused by a later string, is a miss rather than a
        false hit. An entry holds its source, so an accepted entry's identity check can never read a
        freed object.
        """
        entry = self._artifacts.get(key)
        if entry is None:
            return None
        if entry.source is source or entry.digest == _digest(source):
            self._artifacts.move_to_end(key)
            return entry
        return None

    def _store(
        self, kind: str, key: tuple[str, int], source: str, artifact: Any, size: int
    ) -> None:
        """Insert one artifact, then evict by recency until both bounds hold."""
        previous = self._artifacts.pop(key, None)
        if previous is not None:
            self._bytes -= previous.size
        self._artifacts[key] = MaterializedArtifact(
            format=kind,
            source=source,
            artifact=artifact,
            size=size,
            digest=_digest(source),
        )
        self._bytes += size
        self._evict()

    def _evict(self) -> None:
        """LRU eviction under both bounds; the newest entry is never the one evicted.

        A single artifact larger than the byte cap is therefore retained while it is in use, which
        keeps "one document, one parse" true for an input bigger than the cap.
        """
        while len(self._artifacts) > 1 and (
            self._bytes > self._max_bytes or len(self._artifacts) > self._max_items
        ):
            _, evicted = self._artifacts.popitem(last=False)
            self._bytes -= evicted.size


def _digest(source: str) -> str:
    """The content digest of one source text (the fallback half of the key, ``03`` §6)."""
    return blake2b(source.encode("utf-8"), digest_size=_DIGEST_BYTES).hexdigest()


__all__ = [
    "HTML",
    "JSON",
    "XML",
    "Materialize",
    "MaterializedArtifact",
    "Materializer",
]
