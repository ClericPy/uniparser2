"""``SqliteStore``: the two tables of `04` §4.2, one transaction per publish.

``PRAGMA journal_mode=WAL`` is friendly to concurrent readers and there is deliberately **no
foreign key**: an audit row must be able to keep existing after its ``template`` row is deleted
(`04` §4.2). A publish is one ``BEGIN IMMEDIATE`` … ``COMMIT``, so "a chain without an audit row"
and "an audit row without a chain" cannot both appear through this store.

Applicability: multiple writers, SQL queries and gate scans, sharing a database with the host. The
constructor touches no filesystem; the schema is created on the first operation.
"""

from __future__ import annotations

import builtins
import contextlib
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Final

from uniparser2.core.errors import Diagnostic
from uniparser2.core.values import loads_json

from .base import audit_without_chain, chain_without_audit, publish_into, select_entries
from .fingerprint import canonical_graph
from .model import (
    AuditRow,
    Graph,
    PublishResult,
    Source,
    Status,
    Template,
    TemplateMeta,
    meta_of,
)

_SCHEMA: Final[tuple[str, ...]] = (
    """
    CREATE TABLE IF NOT EXISTS template (
      chain_id     TEXT PRIMARY KEY,
      root_domain  TEXT NOT NULL,
      tpl_key      TEXT NOT NULL,
      status       TEXT NOT NULL DEFAULT 'draft',
      source       TEXT NOT NULL DEFAULT 'agent',
      graph        TEXT NOT NULL,
      create_time  TEXT NOT NULL,
      update_time  TEXT NOT NULL,
      UNIQUE(root_domain, tpl_key)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_template_domain ON template(root_domain)",
    "CREATE INDEX IF NOT EXISTS idx_template_status ON template(status)",
    """
    CREATE TABLE IF NOT EXISTS template_audit (
      seq        INTEGER PRIMARY KEY AUTOINCREMENT,
      chain_id   TEXT NOT NULL,
      at         TEXT NOT NULL,
      actor      TEXT NOT NULL,
      source     TEXT NOT NULL,
      old_hash   TEXT,
      new_hash   TEXT NOT NULL,
      note       TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_audit_chain ON template_audit(chain_id, seq)",
)

_SELECT_TEMPLATE_BY_KEY: Final = (
    "SELECT chain_id, root_domain, tpl_key, status, source, graph, create_time, update_time "
    "FROM template WHERE root_domain = ? AND tpl_key = ?"
)
_SELECT_ALL_TEMPLATES: Final = (
    "SELECT chain_id, root_domain, tpl_key, status, source, graph, create_time, update_time "
    "FROM template"
)
_SELECT_AUDIT_BY_CHAIN: Final = (
    "SELECT seq, chain_id, at, actor, source, old_hash, new_hash, note "
    "FROM template_audit WHERE chain_id = ? ORDER BY seq"
)


class SqliteStore:
    """A `TemplateStore` on SQLite (`04` §4.2)."""

    def __init__(self, path: Path) -> None:
        """Remember the database path; the constructor touches no filesystem."""
        self.path = Path(path)

    def get(self, root_domain: str, tpl_key: str) -> Template | None:
        """The stored chain, or ``None``. Performs no ``compile()`` (`04` §4)."""
        with self._connection() as conn:
            row = conn.execute(
                _SELECT_TEMPLATE_BY_KEY,
                (root_domain, tpl_key),
            ).fetchone()
        return None if row is None else _template_of(row)

    def list(
        self, *, root_domain: str | None = None, status: Status | None = None
    ) -> builtins.list[TemplateMeta]:
        """Listing entries, filtered and ordered (`04` §4)."""
        with self._connection() as conn:
            rows = conn.execute(_SELECT_ALL_TEMPLATES).fetchall()
        return select_entries(
            (meta_of(_template_of(row)) for row in rows),
            root_domain=root_domain,
            status=status,
        )

    def publish(
        self,
        graph: Graph,
        *,
        root_domain: str,
        tpl_key: str,
        actor: str,
        source: Source,
        note: str | None = None,
    ) -> PublishResult:
        """The only write entry point; the steps are `04` §5, the transaction its step 6."""
        return publish_into(
            self,
            graph,
            root_domain=root_domain,
            tpl_key=tpl_key,
            actor=actor,
            source=source,
            note=note,
        )

    def audit(self, chain_id: str) -> builtins.list[AuditRow]:
        """The change history of one chain, oldest first: ``ORDER BY seq`` (`04` §4)."""
        with self._connection() as conn:
            rows = conn.execute(_SELECT_AUDIT_BY_CHAIN, (chain_id,)).fetchall()
        return [_audit_of(row) for row in rows]

    def inconsistencies(self) -> builtins.list[Diagnostic]:
        """The `UP2-E3003` findings (`04` §5.1, §10); repaired by :func:`repair_chain`."""
        with self._connection() as conn:
            missing = [
                row[0]
                for row in conn.execute(
                    "SELECT chain_id FROM template WHERE chain_id NOT IN "
                    "(SELECT chain_id FROM template_audit) ORDER BY chain_id"
                )
            ]
            orphan = [
                row[0]
                for row in conn.execute(
                    "SELECT DISTINCT chain_id FROM template_audit WHERE chain_id NOT IN "
                    "(SELECT chain_id FROM template) ORDER BY chain_id"
                )
            ]
        return [chain_without_audit(chain_id) for chain_id in missing] + [
            audit_without_chain(chain_id) for chain_id in orphan
        ]

    def find_chain(self, chain_id: str) -> Template | None:
        """The row one ``chain_id`` names, if this store holds it (`up2 doctor --fix`)."""
        with self._connection() as conn:
            row = conn.execute(
                "SELECT chain_id, root_domain, tpl_key, status, source, graph, create_time, "
                "update_time FROM template WHERE chain_id = ?",
                (chain_id,),
            ).fetchone()
        return None if row is None else _template_of(row)

    # -- the StoreBackend seam (04 §5) ---------------------------------------------------------

    def read_template(self, root_domain: str, tpl_key: str) -> Template | None:
        """The same read as ``get``; named after the seam `04` §5 writes through."""
        return self.get(root_domain, tpl_key)

    @contextmanager
    def transaction(self) -> Iterator[_SqliteTransaction]:
        """One ``BEGIN IMMEDIATE`` … ``COMMIT``, on a connection of its own (`04` §5 step 6)."""
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield _SqliteTransaction(conn)
        except BaseException:
            with contextlib.suppress(sqlite3.Error):
                conn.execute("ROLLBACK")
            raise
        else:
            conn.execute("COMMIT")
        finally:
            conn.close()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        for statement in _SCHEMA:
            conn.execute(statement)
        return conn


class _SqliteTransaction:
    """The two writes of one publish, inside the open transaction (`04` §5 steps 4-5)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def write_template(self, template: Template) -> None:
        """Insert, or update the conflicting row in place and keep its identity (`04` §2)."""
        self._conn.execute(
            """
            INSERT INTO template (chain_id, root_domain, tpl_key, status, source, graph,
                                  create_time, update_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(root_domain, tpl_key) DO UPDATE SET
              graph = excluded.graph,
              source = excluded.source,
              update_time = excluded.update_time
            """,
            (
                template.chain_id,
                template.root_domain,
                template.tpl_key,
                template.status,
                template.source,
                canonical_graph(template.graph),
                template.create_time,
                template.update_time,
            ),
        )

    def append_audit(
        self,
        template: Template,
        *,
        actor: str,
        old_hash: str | None,
        new_hash: str,
        note: str | None,
    ) -> int:
        """Append one row; ``seq`` is the table's own auto-increment (`04` §2.1)."""
        cursor = self._conn.execute(
            "INSERT INTO template_audit (chain_id, at, actor, source, old_hash, new_hash, note) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                template.chain_id,
                template.update_time,
                actor,
                template.source,
                old_hash,
                new_hash,
                note,
            ),
        )
        seq = cursor.lastrowid
        if seq is None:  # pragma: no cover - an INSERT always has a rowid
            raise sqlite3.IntegrityError("the audit row got no sequence")
        return seq


def _template_of(row: Sequence[Any]) -> Template:
    """Read a row back as **data** (`01` §8): the graph is parsed, never deserialized."""
    return Template(
        chain_id=row[0],
        root_domain=row[1],
        tpl_key=row[2],
        status=row[3],
        source=row[4],
        graph=loads_json(row[5], subject="the stored graph"),
        create_time=row[6],
        update_time=row[7],
    )


def _audit_of(row: Sequence[Any]) -> AuditRow:
    return AuditRow(
        seq=row[0],
        chain_id=row[1],
        at=row[2],
        actor=row[3],
        source=row[4],
        old_hash=row[5],
        new_hash=row[6],
        note=row[7],
    )
