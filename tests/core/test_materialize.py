"""The run-scoped materialization cache (design doc `03` §6).

The cache is a correctness-of-performance part of the design rather than an optimization, so its
contract is pinned here rather than its speed: a hit is indistinguishable from a miss, the key is
the target format plus the source, both bounds evict by recency, one artifact larger than the byte
cap is retained while it is in use, and a scope's cache is released with the scope.

No timing case lives here on purpose. A wall-clock assertion over a parse would either be flaky on a
loaded machine or so loose that it proves nothing; what the cache promises is the *accounting* — how
many times a source was built, how many bytes and artifacts are retained — and that is what these
cases assert.
"""

from __future__ import annotations

from typing import Any

from uniparser2 import Ok, Scope, compile_field, eval_field
from uniparser2.core import limits
from uniparser2.core.materialize import HTML, XML, Materializer

_JSON_TEXT = '{"a": {"b": 7}}'


class _FakeStr(str):
    """A stand-in source whose hash is deliberate: two of these can collide on purpose.

    ``str`` is immutable, so a subclass is the only way to hand the cache a colliding key.
    """

    __slots__ = ("_memo",)

    _memo: int

    def __new__(cls, text: str, memo: int) -> _FakeStr:
        instance = super().__new__(cls, text)
        instance._memo = memo
        return instance

    def __hash__(self) -> int:
        return self._memo


class _Builds:
    """A builder that records what it was asked to build, so hits and misses are observable."""

    def __init__(self, size: int = 10) -> None:
        self.size = size
        self.calls: list[str] = []
        self.artifacts: list[Any] = []

    def __call__(self, source: str) -> tuple[Any, int]:
        self.calls.append(source)
        artifact = {"source": source}
        self.artifacts.append(artifact)
        return artifact, self.size


def test_the_default_bounds_come_from_the_limits_module() -> None:
    """The cache's caps are the declared resource limits, not a local decision (``01`` §9)."""
    cache = Materializer()
    assert cache.max_bytes == limits.MAX_MATERIALIZE_BYTES
    assert cache.max_items == limits.MAX_MATERIALIZE_ITEMS
    assert Materializer(max_bytes=1, max_items=2).max_items == 2


def test_the_same_object_hits_once() -> None:
    cache = Materializer()
    build = _Builds()
    text = "<p>one</p>"

    first = cache.get(HTML, text, build)
    second = cache.get(HTML, text, build)

    assert first is second
    assert build.calls == [text]
    assert len(cache) == 1
    assert cache.bytes == build.size


def test_an_equal_text_reaches_the_same_entry() -> None:
    """The content fallback: a distinct object of equal content is a hit (``03`` §6)."""
    cache = Materializer()
    build = _Builds()

    assert cache.get(HTML, "<p>one</p>", build) is cache.get(HTML, "<p>one</p>", build)
    assert len(build.calls) == 1
    assert len(cache) == 1


def test_a_different_text_is_a_different_entry() -> None:
    cache = Materializer()
    build = _Builds()

    cache.get(HTML, "<p>one</p>", build)
    cache.get(HTML, "<p>two</p>", build)

    assert len(build.calls) == 2
    assert len(cache) == 2
    assert cache.bytes == 2 * build.size


def test_one_text_in_two_formats_is_two_entries() -> None:
    cache = Materializer()
    build = _Builds()
    text = "<p>one</p>"

    html = cache.get(HTML, text, build)
    xml = cache.get(XML, text, build)

    assert html is not xml
    assert len(build.calls) == 2
    assert len(cache) == 2


def test_a_colliding_key_does_not_hit() -> None:
    """Identity and content are what decide a hit; a hash collision is not a hit (``03`` §6)."""
    cache = Materializer()
    build = _Builds()
    first = _FakeStr("alpha", 7)
    second = _FakeStr("beta", 7)

    cache.get(HTML, first, build)
    artifact = cache.get(HTML, second, build)

    assert len(build.calls) == 2
    assert artifact["source"] == "beta"


def test_a_colliding_key_still_matches_its_own_content() -> None:
    """Once the colliding bucket is filled, the same key and content keeps answering it."""
    cache = Materializer()
    build = _Builds()
    text = _FakeStr("alpha", 7)

    first = cache.get(HTML, text, build)
    assert cache.get(HTML, text, build) is first
    assert len(build.calls) == 1


def test_the_item_bound_evicts_the_least_recently_used() -> None:
    cache = Materializer(max_items=2)
    build = _Builds()

    cache.get(HTML, "a", build)
    cache.get(HTML, "b", build)
    cache.get(HTML, "c", build)

    assert len(cache) == 2
    assert cache.bytes == 2 * build.size
    assert cache.get(HTML, "a", build)["source"] == "a"
    assert len(build.calls) == 4  # a / b / c, then a again after it was evicted


def test_a_read_refreshes_recency() -> None:
    cache = Materializer(max_items=2)
    build = _Builds()

    cache.get(HTML, "a", build)
    cache.get(HTML, "b", build)
    cache.get(HTML, "a", build)  # a becomes the most recently used
    cache.get(HTML, "c", build)  # so b is the one evicted

    assert cache.get(HTML, "a", build)["source"] == "a"
    assert cache.get(HTML, "b", build)["source"] == "b"
    assert [call for call in build.calls if call == "b"] == ["b", "b"]


def test_the_byte_bound_evicts_by_materialized_size() -> None:
    cache = Materializer(max_bytes=25, max_items=8)
    build = _Builds(size=10)

    for name in ("a", "b", "c", "d"):
        cache.get(HTML, name, build)

    assert cache.bytes == 20
    assert len(cache) == 2
    assert cache.get(HTML, "a", build)["source"] == "a"
    assert cache.get(HTML, "d", build)["source"] == "d"


def test_an_artifact_over_the_byte_cap_is_kept_while_in_use() -> None:
    cache = Materializer(max_bytes=5)
    build = _Builds(size=40)

    kept = cache.get(HTML, "huge", build)

    assert cache.bytes == 40  # the cap is soft for the artifact in use
    assert len(cache) == 1
    assert cache.get(HTML, "huge", build) is kept
    assert len(build.calls) == 1


def test_the_over_cap_artifact_is_evicted_once_it_is_replaced() -> None:
    cache = Materializer(max_bytes=5)
    build = _Builds(size=40)

    cache.get(HTML, "huge", build)
    cache.get(HTML, "next", build)

    assert len(cache) == 1
    assert cache.bytes == 40
    assert len(build.calls) == 2


def test_the_last_artifact_is_never_evicted() -> None:
    cache = Materializer(max_bytes=1, max_items=1)
    build = _Builds(size=10)

    cache.get(HTML, "a", build)
    cache.get(HTML, "b", build)

    assert len(cache) == 1
    assert cache.get(HTML, "b", build)["source"] == "b"


def test_a_scope_without_materialization_holds_nothing() -> None:
    scope = Scope()

    assert scope.cache is None
    outcome = eval_field(compile_field([["const", 1]]), None, scope=scope)
    assert isinstance(outcome, Ok)
    assert outcome.value == 1
    assert len(scope.materializer) == 0
    assert scope.materializer.bytes == 0


def test_a_child_scope_shares_the_parents_cache() -> None:
    parent = Scope()
    cache = parent.materializer

    assert parent.child().materializer is cache
    assert parent.cache is cache


def test_clearing_releases_every_artifact() -> None:
    cache = Materializer()
    build = _Builds()
    cache.get(HTML, "a", build)

    cache.clear()

    assert len(cache) == 0
    assert cache.bytes == 0
    assert cache.get(HTML, "a", build)["source"] == "a"
    assert len(build.calls) == 2


def test_the_consumer_measures_a_json_tree_by_its_own_footprint() -> None:
    """A JSON tree is thousands of Python objects, so its text would understate it (``03`` §6)."""
    scope = Scope()
    outcome = eval_field(compile_field([["json", "a.b"]]), _JSON_TEXT, scope=scope)
    assert isinstance(outcome, Ok)
    assert outcome.value == 7

    cache = scope.materializer
    assert len(cache) == 1
    assert cache.bytes > len(_JSON_TEXT.encode("utf-8"))
