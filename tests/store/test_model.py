"""The storage models and the fingerprint (design doc 04 §2, §2.1, §3)."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import get_args

from uniparser2.store import canonical_graph, graph_hash, new_chain_id, utc_now
from uniparser2.store.model import Source, Status, Template

HEX32 = re.compile(r"^[0-9a-f]{32}$")
GRAPH = [["css1", "text", "h1"], ["py", "strip", ""]]


def test_new_chain_id_is_uuid4_hex_and_unique() -> None:
    first, second = new_chain_id(), new_chain_id()
    assert HEX32.match(first), first
    assert first != second


def test_utc_now_is_iso8601_utc() -> None:
    stamp = utc_now()
    assert stamp.endswith("+00:00")
    assert datetime.fromisoformat(stamp).utcoffset() is not None


def test_fingerprint_is_32_hex() -> None:
    digest = graph_hash(GRAPH)
    assert HEX32.match(digest), digest


def test_fingerprint_ignores_key_order_and_json_roundtrip() -> None:
    """The same graph fingerprints the same from a JSON file and from a dictionary (04 §3)."""
    bundle = {
        "steps": [{"name": "a", "body": {"t": ["css1", "text", "h1"]}, "collect": True}],
        "collect": "a",
    }
    reordered = {
        "collect": "a",
        "steps": [{"body": {"t": ["css1", "text", "h1"]}, "name": "a", "collect": True}],
    }
    loaded = json.loads(json.dumps(bundle, ensure_ascii=False))
    assert graph_hash(bundle) == graph_hash(reordered) == graph_hash(loaded)
    assert canonical_graph(bundle) == json.dumps(
        bundle, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def test_fingerprint_keeps_chinese_unescaped_and_drops_whitespace() -> None:
    assert canonical_graph({"tpl_key": "政府文件列表"}) == '{"tpl_key":"政府文件列表"}'


def test_fingerprint_covers_the_graph_alone() -> None:
    """``status`` / ``source`` are not arguments of the fingerprint at all (04 §3)."""
    assert graph_hash(GRAPH) == graph_hash(json.loads(json.dumps(GRAPH)))
    assert graph_hash(GRAPH) != graph_hash([["css1", "text", "h2"]])


def test_template_carries_no_dsl_version() -> None:
    """``dsl_version`` was deleted (04 §3, D-04-3): the compiler is the dialect check."""
    assert set(Template.__dataclass_fields__) == {
        "chain_id",
        "root_domain",
        "tpl_key",
        "status",
        "source",
        "graph",
        "create_time",
        "update_time",
    }


def test_status_and_source_vocabularies() -> None:
    assert get_args(Status.__value__) == ("draft", "ready", "disabled")
    assert get_args(Source.__value__) == ("human", "agent", "import")
