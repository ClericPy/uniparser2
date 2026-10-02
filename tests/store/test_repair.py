"""`up2 doctor --fix` at the store layer: both implementations repair identically (04 §10).

The command is `tests/cli/test_snapshot.py`'s business; what is asserted here is the repair itself
-- one synthesized audit row, carrying the stored graph's fingerprint -- and that it is the same on
the file store and on SQLite.
"""

from __future__ import annotations

import contextlib
import sqlite3
from pathlib import Path

import pytest

from uniparser2.store import FileStore, Graph, SqliteStore, graph_hash, repair_chain

GRAPH: Graph = [["css1", "text", "h1"]]
DOMAIN = "local"
KEY = "t1"
ACTOR = "doctor"
NOTE = "written by `up2 doctor --fix`: this chain had no audit row"


def make_store(kind: str, tmp_path: Path) -> FileStore | SqliteStore:
    if kind == "sqlite":
        return SqliteStore(tmp_path / "store.sqlite3")
    return FileStore(tmp_path / "home")


@pytest.fixture(params=["file", "sqlite"])
def store(request: pytest.FixtureRequest, tmp_path: Path) -> FileStore | SqliteStore:
    return make_store(request.param, tmp_path)


def drop_audit(store: FileStore | SqliteStore) -> None:
    """Lose the audit rows the way a crash in the file store's write window would (04 §5 step 6)."""
    if isinstance(store, FileStore):
        store.audit_path(DOMAIN, KEY).unlink()
        return
    with contextlib.closing(sqlite3.connect(store.path)) as conn:
        conn.execute("DELETE FROM template_audit")
        conn.commit()


def test_repair_writes_the_missing_audit_row(store: FileStore | SqliteStore) -> None:
    published = store.publish(GRAPH, root_domain=DOMAIN, tpl_key=KEY, actor="me", source="human")
    drop_audit(store)
    assert len(store.inconsistencies()) == 1

    row = repair_chain(store, published.chain_id, actor=ACTOR, note=NOTE)
    assert row is not None
    assert (row.chain_id, row.actor, row.note) == (published.chain_id, ACTOR, NOTE)
    assert row.old_hash is None
    assert row.new_hash == graph_hash(GRAPH) == published.new_hash
    assert row.source == "human"
    assert store.inconsistencies() == []
    assert [item.new_hash for item in store.audit(published.chain_id)] == [row.new_hash]


def test_repair_is_a_no_op_for_an_unknown_chain(store: FileStore | SqliteStore) -> None:
    """A finding whose chain is already gone is left alone: there is nothing to write beside."""
    store.publish(GRAPH, root_domain=DOMAIN, tpl_key=KEY, actor="me", source="agent")
    assert repair_chain(store, "0" * 32, actor=ACTOR, note=NOTE) is None
    assert store.inconsistencies() == []


def test_repair_numbers_the_row_it_writes(tmp_path: Path) -> None:
    """A repair appends one row to an empty file: nothing of the lost history is invented."""
    store = FileStore(tmp_path / "home")
    published = store.publish(GRAPH, root_domain=DOMAIN, tpl_key=KEY, actor="me", source="agent")
    store.publish(
        [["css1", "text", "h2"]],
        root_domain=DOMAIN,
        tpl_key=KEY,
        actor="me",
        source="agent",
        note="second",
    )
    store.audit_path(DOMAIN, KEY).unlink()
    repair_chain(store, published.chain_id, actor=ACTOR, note=NOTE)
    rows = store.audit(published.chain_id)
    assert [(row.seq, row.note, row.old_hash) for row in rows] == [(1, NOTE, None)]
