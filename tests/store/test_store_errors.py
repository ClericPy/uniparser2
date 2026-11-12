"""One case per storage error code, on both implementations (design doc 04 §5.1).

| code | case |
|---|---|
| ``UP2-E3001`` | a row that reads back with a different fingerprint (a concurrent writer) |
| ``UP2-E3002`` | an illegal ``tpl_key`` / an empty ``root_domain``, before anything is written |
| ``UP2-E3003`` | a chain without an audit row, and an audit row without a chain |
| ``UP2-E3004`` | a store whose location cannot be written |
| ``UP2-E3005`` | ``--skip-tests`` without ``--note`` (the gate, not the store) |
"""

from __future__ import annotations

import contextlib
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from uniparser2.core.errors import Up2Error
from uniparser2.store import FileStore, Graph, SqliteStore, gate_skip_tests
from uniparser2.store.model import Template

GRAPH: Graph = [["css1", "text", "h1"]]
OTHER_GRAPH: Graph = [["css1", "text", "h2"]]
RACED_GRAPH: Graph = [["css1", "text", "h3"]]
DOMAIN = "local"
KEY = "t1"


class RacingFileStore(FileStore):
    """A second writer that replaced the row between our read and our read-back (04 §5.1)."""

    def read_template(self, root_domain: str, tpl_key: str) -> Template | None:
        stored = super().read_template(root_domain, tpl_key)
        return None if stored is None else replace(stored, graph=RACED_GRAPH)


class RacingSqliteStore(SqliteStore):
    """The same race on SQLite."""

    def read_template(self, root_domain: str, tpl_key: str) -> Template | None:
        stored = super().read_template(root_domain, tpl_key)
        return None if stored is None else replace(stored, graph=RACED_GRAPH)


def make_store(kind: str, tmp_path: Path) -> FileStore | SqliteStore:
    if kind == "sqlite":
        return SqliteStore(tmp_path / "store.sqlite3")
    return FileStore(tmp_path / "home")


@pytest.fixture(params=["file", "sqlite"])
def store(request: pytest.FixtureRequest, tmp_path: Path) -> FileStore | SqliteStore:
    return make_store(request.param, tmp_path)


def test_fingerprint_conflict_is_reported(tmp_path: Path) -> None:
    """``UP2-E3001``: the graph written under the key is not the expected fingerprint."""
    for racing in (
        RacingFileStore(tmp_path / "file-home"),
        RacingSqliteStore(tmp_path / "db.sqlite3"),
    ):
        with pytest.raises(Up2Error) as caught:
            racing.publish(GRAPH, root_domain=DOMAIN, tpl_key=KEY, actor="me", source="agent")
        diagnostic = caught.value.diagnostic
        assert diagnostic.code == "UP2-E3001"
        assert "expected fingerprint" in diagnostic.message
        assert "up2 get" in diagnostic.fix


@pytest.mark.parametrize("tpl_key", ["", "a:b", "a/b", ".draft", "-draft", "a" * 65])
def test_an_illegal_key_is_refused(store: FileStore | SqliteStore, tpl_key: str) -> None:
    """``UP2-E3002``: the character set is checked before anything is written (04 §2, §5 step 1)."""
    with pytest.raises(Up2Error) as caught:
        store.publish(GRAPH, root_domain=DOMAIN, tpl_key=tpl_key, actor="me", source="agent")
    diagnostic = caught.value.diagnostic
    assert diagnostic.code == "UP2-E3002"
    assert repr(tpl_key) in diagnostic.message
    assert r"[\w\u4e00-\u9fff]" in diagnostic.message
    assert store.list() == []


def test_an_empty_domain_is_refused(store: FileStore | SqliteStore) -> None:
    """``UP2-E3002``: ``root_domain`` is the other half of the identity."""
    with pytest.raises(Up2Error) as caught:
        store.publish(GRAPH, root_domain="", tpl_key=KEY, actor="me", source="agent")
    assert caught.value.diagnostic.code == "UP2-E3002"
    assert "root_domain" in caught.value.diagnostic.message
    assert store.list() == []


def test_a_legal_key_is_accepted(store: FileStore | SqliteStore) -> None:
    """The boundary of the character set: Chinese, digits, underscores, dots and hyphens."""
    store.publish(
        GRAPH, root_domain=DOMAIN, tpl_key="政府文件列表-v2.1_x", actor="me", source="agent"
    )
    assert store.get(DOMAIN, "政府文件列表-v2.1_x") is not None


@pytest.mark.parametrize("root_domain", [".", "..", "../escape", "a/b", "a\\b"])
def test_a_domain_that_is_not_one_path_component_is_refused(
    store: FileStore | SqliteStore, root_domain: str
) -> None:
    """``UP2-E3002``: the file store uses the domain as a directory name, so a separator escapes."""
    with pytest.raises(Up2Error) as caught:
        store.publish(GRAPH, root_domain=root_domain, tpl_key=KEY, actor="me", source="agent")
    assert caught.value.diagnostic.code == "UP2-E3002"
    assert store.list() == []


def test_a_read_path_checks_the_identity_too(tmp_path: Path) -> None:
    """A traversal domain must not read outside the store root on ``get`` / ``audit``."""
    store = FileStore(tmp_path / "home")
    with pytest.raises(Up2Error) as caught:
        store.get("../escape", KEY)
    assert caught.value.diagnostic.code == "UP2-E3002"


def test_a_chain_without_an_audit_row_is_reported(tmp_path: Path) -> None:
    """``UP2-E3003``: the file store's crash window, and a hand-deleted audit table."""
    file_store = FileStore(tmp_path / "home")
    result = file_store.publish(GRAPH, root_domain=DOMAIN, tpl_key=KEY, actor="me", source="agent")
    assert file_store.inconsistencies() == []
    file_store.audit_path(DOMAIN, KEY).unlink()
    findings = file_store.inconsistencies()
    assert [finding.code for finding in findings] == ["UP2-E3003"]
    assert result.chain_id in findings[0].message

    sqlite_store = SqliteStore(tmp_path / "store.sqlite3")
    stored = sqlite_store.publish(
        GRAPH, root_domain=DOMAIN, tpl_key=KEY, actor="me", source="agent"
    )
    with contextlib.closing(sqlite3.connect(sqlite_store.path)) as conn:
        conn.execute("DELETE FROM template_audit")
        conn.commit()
    findings = sqlite_store.inconsistencies()
    assert [finding.code for finding in findings] == ["UP2-E3003"]
    assert stored.chain_id in findings[0].message


def test_an_audit_row_without_a_chain_is_reported(tmp_path: Path) -> None:
    """``UP2-E3003``: an audit row outlives its template row (04 §4.2 refuses a foreign key)."""
    file_store = FileStore(tmp_path / "home")
    result = file_store.publish(GRAPH, root_domain=DOMAIN, tpl_key=KEY, actor="me", source="agent")
    file_store.chain_path(DOMAIN, KEY).unlink()
    findings = file_store.inconsistencies()
    assert [finding.code for finding in findings] == ["UP2-E3003"]
    assert result.chain_id in findings[0].message

    sqlite_store = SqliteStore(tmp_path / "store.sqlite3")
    sqlite_store.publish(GRAPH, root_domain=DOMAIN, tpl_key=KEY, actor="me", source="agent")
    with contextlib.closing(sqlite3.connect(sqlite_store.path)) as conn:
        conn.execute("DELETE FROM template")
        conn.commit()
    findings = sqlite_store.inconsistencies()
    assert [finding.code for finding in findings] == ["UP2-E3003"]
    assert "no chain" in findings[0].message


def test_a_store_that_cannot_be_written_is_reported(tmp_path: Path) -> None:
    """``UP2-E3004``: a blocked directory on the file store, a blocked path on SQLite."""
    home = tmp_path / "home"
    (home / "chains").parent.mkdir(parents=True)
    (home / "chains").write_text("not a directory", encoding="utf-8")
    with pytest.raises(Up2Error) as caught:
        FileStore(home).publish(GRAPH, root_domain=DOMAIN, tpl_key=KEY, actor="me", source="agent")
    assert caught.value.diagnostic.code == "UP2-E3004"
    assert "chains" in caught.value.diagnostic.message
    assert FileStore(home).audit_path(DOMAIN, KEY).exists() is False

    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory", encoding="utf-8")
    with pytest.raises(Up2Error) as caught:
        SqliteStore(blocked / "store.sqlite3").publish(
            GRAPH, root_domain=DOMAIN, tpl_key=KEY, actor="me", source="agent"
        )
    assert caught.value.diagnostic.code == "UP2-E3004"
    assert "blocked" in caught.value.diagnostic.message


def test_skipping_the_tests_without_a_note_is_refused() -> None:
    """``UP2-E3005``: the bypass must leave a trace (04 §6 G2)."""
    diagnostic = gate_skip_tests(skip_tests=True, note=None)
    assert diagnostic is not None
    assert diagnostic.code == "UP2-E3005"
    assert "--note" in diagnostic.fix
    assert gate_skip_tests(skip_tests=True, note="samples are not ready") is None
    assert gate_skip_tests(skip_tests=False, note=None) is None


def test_the_key_is_checked_before_the_store_is_touched(tmp_path: Path) -> None:
    """Order of the steps: a bad identity and a bad chain write nothing at all (04 §5 steps 1-2)."""
    store = FileStore(tmp_path / "home")
    with pytest.raises(Up2Error) as caught:
        store.publish(
            [["nosuchoperator", "x", "y"]],
            root_domain=DOMAIN,
            tpl_key="a:b",
            actor="m",
            source="agent",
        )
    assert caught.value.diagnostic.code == "UP2-E3002"
    with pytest.raises(Up2Error) as caught:
        store.publish(
            [["nosuchoperator", "x", "y"]],
            root_domain=DOMAIN,
            tpl_key=KEY,
            actor="m",
            source="agent",
        )
    assert caught.value.diagnostic.code == "UP2-E1001"
    assert not (tmp_path / "home").exists()


def test_a_break_in_the_write_window_is_detected(tmp_path: Path, monkeypatch) -> None:
    """The file store lands ``chains`` first, so an audit failure leaves an E3003 finding.

    The window is visible on the chain that was being created: a lost audit row for an *existing*
    chain is indistinguishable from "the chain did not change", because audit rows hold fingerprints
    only (`04` §2.1, §5).
    """
    store = FileStore(tmp_path / "home")
    first = store.publish(GRAPH, root_domain=DOMAIN, tpl_key=KEY, actor="me", source="agent")

    def failing_audit(*args: object, **kwargs: object) -> int:
        raise OSError("disk full")

    monkeypatch.setattr(store, "append_audit", failing_audit)
    with pytest.raises(Up2Error) as caught:
        store.publish(OTHER_GRAPH, root_domain=DOMAIN, tpl_key="t2", actor="me", source="agent")
    assert caught.value.diagnostic.code == "UP2-E3004"
    assert "disk full" in caught.value.diagnostic.message
    assert store.get(DOMAIN, "t2") is not None
    assert [finding.code for finding in store.inconsistencies()] == ["UP2-E3003"]
    # The chain that was updated before the failure keeps its history.
    assert len(store.audit(first.chain_id)) == 1
