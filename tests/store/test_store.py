"""Both implementations, side by side (design doc 04 §4, §5).

Every case runs twice, once per store, so "identical semantics in both Stores" is asserted rather
than promised. ``tmp_path`` is the store location, the way ``UP2_HOME`` is in production.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from uniparser2.core.errors import Up2Error
from uniparser2.store import (
    FileStore,
    Graph,
    SqliteStore,
    graph_hash,
    new_chain_id,
    open_store,
    template_dict,
)
from uniparser2.store.model import Template

GRAPH: Graph = [["css1", "text", "h1"]]
OTHER_GRAPH: Graph = [["css1", "text", "h2"]]
DOMAIN = "local"
KEY = "t1"


def make_store(kind: str, tmp_path: Path) -> FileStore | SqliteStore:
    if kind == "sqlite":
        return SqliteStore(tmp_path / "store.sqlite3")
    return FileStore(tmp_path / "home")


@pytest.fixture(params=["file", "sqlite"])
def store(request: pytest.FixtureRequest, tmp_path: Path) -> FileStore | SqliteStore:
    return make_store(request.param, tmp_path)


def rewrite_graph(
    store: FileStore | SqliteStore, graph: object, *, root_domain: str = DOMAIN, tpl_key: str = KEY
) -> None:
    """Hand-edit the stored graph, the way a person or another tool would."""
    if isinstance(store, FileStore):
        path = store.chain_path(root_domain, tpl_key)
        data = json.loads(path.read_text(encoding="utf-8"))
        data["graph"] = graph
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8", newline="\n")
        return
    with contextlib.closing(sqlite3.connect(store.path)) as conn:
        conn.execute(
            "UPDATE template SET graph = ? WHERE root_domain = ? AND tpl_key = ?",
            (json.dumps(graph), root_domain, tpl_key),
        )
        conn.commit()


def set_status(store: FileStore | SqliteStore, status: str) -> None:
    """A status is set by hand in this slice: no command writes it (04 §2, §6 G3)."""
    if isinstance(store, FileStore):
        path = store.chain_path(DOMAIN, KEY)
        data = json.loads(path.read_text(encoding="utf-8"))
        data["status"] = status
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8", newline="\n")
        return
    with contextlib.closing(sqlite3.connect(store.path)) as conn:
        conn.execute("UPDATE template SET status = ?", (status,))
        conn.commit()


def test_publish_then_get_roundtrip(store: FileStore | SqliteStore) -> None:
    result = store.publish(
        GRAPH, root_domain=DOMAIN, tpl_key=KEY, actor="llm:claude", source="agent", note="first"
    )
    stored = store.get(DOMAIN, KEY)
    assert stored is not None
    assert result.changed is True
    assert result.audit_seq == 1
    assert result.old_hash is None
    assert result.new_hash == graph_hash(GRAPH)
    assert result.chain_id == stored.chain_id
    assert len(result.chain_id) == 32 and result.chain_id.islower()
    assert (stored.status, stored.source, stored.graph) == ("draft", "agent", GRAPH)
    assert stored.create_time == stored.update_time
    assert stored.create_time.endswith("+00:00")
    rows = store.audit(stored.chain_id)
    assert [(row.seq, row.old_hash, row.new_hash, row.actor, row.note) for row in rows] == [
        (1, None, result.new_hash, "llm:claude", "first")
    ]


def test_a_missing_chain_is_none_and_not_listed(store: FileStore | SqliteStore) -> None:
    assert store.get(DOMAIN, "nope") is None
    assert store.audit(new_chain_id()) == []
    assert store.list() == []


def test_list_answers_metadata_without_the_graph(store: FileStore | SqliteStore) -> None:
    assert store.get(DOMAIN, KEY) is None
    store.publish(GRAPH, root_domain="b.example", tpl_key="b", actor="me", source="human")
    store.publish(GRAPH, root_domain="a.example", tpl_key="a", actor="me", source="agent")
    store.publish(OTHER_GRAPH, root_domain="a.example", tpl_key="c", actor="me", source="import")
    listed = store.list()
    assert [(meta.root_domain, meta.tpl_key) for meta in listed] == [
        ("a.example", "a"),
        ("a.example", "c"),
        ("b.example", "b"),
    ]
    assert all(not hasattr(meta, "graph") for meta in listed)
    assert [meta.tpl_key for meta in store.list(root_domain="a.example", status="draft")] == [
        "a",
        "c",
    ]
    assert store.list(status="ready") == []
    assert store.list(root_domain="nope") == []


def test_re_publishing_an_unchanged_graph_writes_nothing(store: FileStore | SqliteStore) -> None:
    first = store.publish(GRAPH, root_domain=DOMAIN, tpl_key=KEY, actor="me", source="agent")
    stored = store.get(DOMAIN, KEY)
    assert stored is not None
    second = store.publish(
        json.loads(json.dumps(GRAPH)),
        root_domain=DOMAIN,
        tpl_key=KEY,
        actor="other",
        source="human",
    )
    assert second.changed is False
    assert second.audit_seq is None
    assert second.chain_id == first.chain_id
    assert second.old_hash == second.new_hash == first.new_hash
    after = store.get(DOMAIN, KEY)
    assert after is not None
    # No row was written at all: not the graph, not the source, not the timestamp.
    assert after == stored
    assert len(store.audit(first.chain_id)) == 1


def test_a_status_change_is_not_a_chain_change(store: FileStore | SqliteStore) -> None:
    first = store.publish(GRAPH, root_domain=DOMAIN, tpl_key=KEY, actor="me", source="agent")
    set_status(store, "ready")
    again = store.publish(GRAPH, root_domain=DOMAIN, tpl_key=KEY, actor="me", source="agent")
    assert again.changed is False
    assert len(store.audit(first.chain_id)) == 1
    stored = store.get(DOMAIN, KEY)
    assert stored is not None and stored.status == "ready"


def test_re_publishing_updates_in_place(store: FileStore | SqliteStore) -> None:
    first = store.publish(GRAPH, root_domain=DOMAIN, tpl_key=KEY, actor="me", source="human")
    before = store.get(DOMAIN, KEY)
    assert before is not None
    set_status(store, "ready")
    second = store.publish(
        OTHER_GRAPH, root_domain=DOMAIN, tpl_key=KEY, actor="ops", source="import"
    )
    after = store.get(DOMAIN, KEY)
    assert after is not None
    assert second.changed is True and second.audit_seq == 2
    assert after.chain_id == before.chain_id
    assert after.create_time == before.create_time
    assert after.status == "ready"
    assert after.source == "import"
    assert after.graph == OTHER_GRAPH
    assert after.update_time >= before.update_time
    rows = store.audit(first.chain_id)
    assert [(row.seq, row.old_hash, row.new_hash) for row in rows] == [
        (1, None, graph_hash(GRAPH)),
        (2, graph_hash(GRAPH), graph_hash(OTHER_GRAPH)),
    ]


def test_rollback_leaves_an_audit_row(store: FileStore | SqliteStore) -> None:
    first = store.publish(GRAPH, root_domain=DOMAIN, tpl_key=KEY, actor="me", source="agent")
    store.publish(OTHER_GRAPH, root_domain=DOMAIN, tpl_key=KEY, actor="me", source="agent")
    store.publish(
        GRAPH, root_domain=DOMAIN, tpl_key=KEY, actor="ops:me", source="human", note="roll back"
    )
    rows = store.audit(first.chain_id)
    assert [row.note for row in rows] == [None, None, "roll back"]
    assert rows[-1].new_hash == rows[0].new_hash
    assert len(rows) == 3


def test_recompile_on_read(store: FileStore | SqliteStore) -> None:
    """A stored graph that no longer compiles is reported, never silently overwritten (01 §8)."""
    store.publish(GRAPH, root_domain=DOMAIN, tpl_key=KEY, actor="me", source="agent")
    rewrite_graph(store, [["nosuchoperator", "x", "y"]])
    with pytest.raises(Up2Error) as caught:
        store.publish(OTHER_GRAPH, root_domain=DOMAIN, tpl_key=KEY, actor="me", source="agent")
    assert caught.value.diagnostic.code == "UP2-E1001"
    stored = store.get(DOMAIN, KEY)
    assert stored is not None and stored.graph == [["nosuchoperator", "x", "y"]]


def test_the_store_returns_data_not_a_compilation_product(store: FileStore | SqliteStore) -> None:
    store.publish(GRAPH, root_domain=DOMAIN, tpl_key=KEY, actor="me", source="agent")
    first = store.get(DOMAIN, KEY)
    second = store.get(DOMAIN, KEY)
    assert first is not None and second is not None
    assert first.graph == GRAPH and first.graph is not second.graph
    assert isinstance(first, Template)


def test_a_bad_chain_leaves_no_residue(store: FileStore | SqliteStore) -> None:
    with pytest.raises(Up2Error) as caught:
        store.publish(
            [["nosuchoperator", "x", "y"]],
            root_domain=DOMAIN,
            tpl_key=KEY,
            actor="me",
            source="agent",
        )
    assert caught.value.diagnostic.code == "UP2-E1001"
    assert store.get(DOMAIN, KEY) is None
    assert store.list() == []


def test_the_clock_is_injectable(monkeypatch, tmp_path: Path) -> None:
    import uniparser2.store.base as base

    stamp = "2026-01-01T00:00:00+00:00"
    monkeypatch.setattr(base, "utc_now", lambda: stamp)
    store = FileStore(tmp_path / "home")
    store.publish(GRAPH, root_domain=DOMAIN, tpl_key=KEY, actor="me", source="agent")
    stored = store.get(DOMAIN, KEY)
    assert stored is not None
    assert (stored.create_time, stored.update_time) == (stamp, stamp)
    assert store.audit(stored.chain_id)[0].at == stamp


def test_the_chain_file_is_canonical_and_atomic(tmp_path: Path) -> None:
    """Sorted keys and no temporary file left behind (04 §4.1)."""
    store = FileStore(tmp_path / "home")
    store.publish(GRAPH, root_domain=DOMAIN, tpl_key=KEY, actor="me", source="agent")
    path = store.chain_path(DOMAIN, KEY)
    text = path.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert list(json.loads(text)) == sorted(json.loads(text))
    assert [item.name for item in path.parent.iterdir()] == [path.name]
    assert store.audit_path(DOMAIN, KEY).read_text(encoding="utf-8").count("\n") == 1


def test_the_sqlite_schema_is_the_designed_one(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "store.sqlite3")
    store.publish(GRAPH, root_domain=DOMAIN, tpl_key=KEY, actor="me", source="agent")
    with contextlib.closing(sqlite3.connect(store.path)) as conn:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(template)")]
        audit_columns = [row[1] for row in conn.execute("PRAGMA table_info(template_audit)")]
        indexes = {row[1] for row in conn.execute("PRAGMA index_list(template)")}
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        foreign_keys = conn.execute("PRAGMA foreign_key_list(template_audit)").fetchall()
    assert columns == [
        "chain_id",
        "root_domain",
        "tpl_key",
        "status",
        "source",
        "graph",
        "create_time",
        "update_time",
    ]
    assert audit_columns == [
        "seq",
        "chain_id",
        "at",
        "actor",
        "source",
        "old_hash",
        "new_hash",
        "note",
    ]
    assert {"sqlite_autoindex_template_1", "idx_template_domain", "idx_template_status"} <= indexes
    assert mode == "wal"
    assert foreign_keys == []


def test_sqlite_stores_the_graph_as_text(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "store.sqlite3")
    store.publish(GRAPH, root_domain=DOMAIN, tpl_key=KEY, actor="me", source="agent")
    with contextlib.closing(sqlite3.connect(store.path)) as conn:
        stored = conn.execute("SELECT graph FROM template").fetchone()[0]
    assert isinstance(stored, str)
    assert json.loads(stored) == GRAPH


def test_each_chain_gets_its_own_identity_and_history(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "store.sqlite3")
    first = store.publish(GRAPH, root_domain=DOMAIN, tpl_key="a", actor="me", source="agent")
    second = store.publish(GRAPH, root_domain=DOMAIN, tpl_key="b", actor="me", source="agent")
    assert first.chain_id != second.chain_id
    assert len(store.audit(first.chain_id)) == 1
    assert len(store.audit(second.chain_id)) == 1


def test_audit_stays_reachable_after_the_chain_file_is_gone(tmp_path: Path) -> None:
    """The audit is keyed by ``chain_id`` and the layout by key, so it scans (04 §4.1, §4.2)."""
    store = FileStore(tmp_path / "home")
    result = store.publish(GRAPH, root_domain=DOMAIN, tpl_key=KEY, actor="me", source="agent")
    store.chain_path(DOMAIN, KEY).unlink()
    rows = store.audit(result.chain_id)
    assert [row.new_hash for row in rows] == [result.new_hash]


def test_template_dict_carries_the_fingerprint(tmp_path: Path) -> None:
    store = FileStore(tmp_path / "home")
    result = store.publish(GRAPH, root_domain=DOMAIN, tpl_key=KEY, actor="me", source="agent")
    stored = store.get(DOMAIN, KEY)
    assert stored is not None
    payload = template_dict(stored)
    assert payload["graph_hash"] == result.new_hash
    assert payload["graph"] == GRAPH
    assert payload["chain_id"] == result.chain_id


def test_open_store_picks_from_configuration(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("UP2_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("UP2_STORE", raising=False)
    default_store = open_store()
    assert isinstance(default_store, FileStore)
    assert default_store.home == tmp_path / "home"
    monkeypatch.setenv("UP2_STORE", "sqlite")
    sqlite_store = open_store()
    assert isinstance(sqlite_store, SqliteStore)
    assert sqlite_store.path == tmp_path / "home" / "store.sqlite3"
    monkeypatch.setenv("UP2_STORE", "mysql")
    with pytest.raises(ValueError, match="UP2_STORE"):
        open_store()
    assert isinstance(open_store("file", home=tmp_path / "explicit"), FileStore)


def test_default_home_is_the_environment_variable(monkeypatch, tmp_path: Path) -> None:
    from uniparser2.store import default_home

    monkeypatch.setenv("UP2_HOME", str(tmp_path / "override"))
    assert default_home() == tmp_path / "override"
    monkeypatch.delenv("UP2_HOME")
    assert default_home().name == ".uniparser2"


def test_replace_keeps_the_dataclass_frozen(tmp_path: Path) -> None:
    """The models are immutable values, so a fake store cannot mutate a row in place."""
    store = FileStore(tmp_path / "home")
    store.publish(GRAPH, root_domain=DOMAIN, tpl_key=KEY, actor="me", source="agent")
    stored = store.get(DOMAIN, KEY)
    assert stored is not None
    with pytest.raises(FrozenInstanceError):
        # Direct assignment is what a store would try; the dataclass refuses it (a constant
        # ``setattr`` call is the same thing, hence the explicit form ruff prefers here).
        stored.__setattr__("status", "ready")
    assert replace(stored, status="ready").status == "ready"
