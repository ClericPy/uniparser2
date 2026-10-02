"""The template store: the L3 binding layer (`04` §1-§6).

This package is the **only layer allowed to touch disk** (`01` §1): it binds an identity-free chain
to a business identity ``(root_domain, tpl_key)``, freezes it as a ``Template`` row, and keeps an
append-only audit of fingerprints. It depends on ``core``'s public interface and never the other way
round, so the kernel stays stdlib-only, IO-free and unaware that a store exists.

The configuration both ``cli`` and a host read:

- ``UP2_HOME`` -- where the store lives (default ``~/.uniparser2``, `04` §4.1);
- ``UP2_STORE`` -- ``file`` (the default, `04` §4.1) or ``sqlite``, whose database is
  ``$UP2_HOME/store.sqlite3``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final, Literal

from .base import (
    DoctorBackend,
    StoreBackend,
    TemplateStore,
    Transaction,
    lint_graph,
    publish_into,
    repair_chain,
)
from .file import FileStore
from .fingerprint import canonical_graph, graph_hash
from .gates import gate_overwrite, gate_skip_tests
from .model import (
    AuditRow,
    Graph,
    PublishResult,
    Source,
    Status,
    Template,
    TemplateMeta,
    meta_of,
    new_chain_id,
    utc_now,
)
from .sqlite import SqliteStore

HOME_ENV: Final = "UP2_HOME"
STORE_ENV: Final = "UP2_STORE"
DEFAULT_HOME_NAME: Final = ".uniparser2"
SQLITE_FILE_NAME: Final = "store.sqlite3"

type StoreKind = Literal["file", "sqlite"]

__all__ = [
    "DEFAULT_HOME_NAME",
    "HOME_ENV",
    "SQLITE_FILE_NAME",
    "STORE_ENV",
    "AuditRow",
    "DoctorBackend",
    "FileStore",
    "Graph",
    "PublishResult",
    "Source",
    "SqliteStore",
    "Status",
    "StoreBackend",
    "StoreKind",
    "Template",
    "TemplateMeta",
    "TemplateStore",
    "Transaction",
    "audit_row_dict",
    "canonical_graph",
    "default_home",
    "gate_overwrite",
    "gate_skip_tests",
    "graph_hash",
    "lint_graph",
    "meta_of",
    "new_chain_id",
    "open_store",
    "publish_into",
    "repair_chain",
    "template_dict",
    "utc_now",
]


def default_home() -> Path:
    """``$UP2_HOME``, or ``~/.uniparser2`` (`04` §4.1)."""
    override = os.environ.get(HOME_ENV)
    return Path(override) if override else Path.home() / DEFAULT_HOME_NAME


def open_store(
    kind: StoreKind | None = None, *, home: Path | None = None
) -> FileStore | SqliteStore:
    """Pick the implementation from configuration (`04` §4): ``file`` unless ``UP2_STORE`` says."""
    chosen = kind if kind is not None else os.environ.get(STORE_ENV, "file")
    root = home if home is not None else default_home()
    if chosen == "sqlite":
        return SqliteStore(root / SQLITE_FILE_NAME)
    if chosen != "file":
        raise ValueError(f"{STORE_ENV} must be 'file' or 'sqlite', got {chosen!r}")
    return FileStore(root)


def template_dict(template: Template) -> dict[str, object]:
    """A ``Template`` as JSON data, with the fingerprint of its graph (`up2 get`)."""
    return {
        "chain_id": template.chain_id,
        "root_domain": template.root_domain,
        "tpl_key": template.tpl_key,
        "status": template.status,
        "source": template.source,
        "graph": template.graph,
        "graph_hash": graph_hash(template.graph),
        "create_time": template.create_time,
        "update_time": template.update_time,
    }


def audit_row_dict(row: AuditRow) -> dict[str, object]:
    """An ``AuditRow`` as JSON data (`up2 audit --json`)."""
    return {
        "seq": row.seq,
        "chain_id": row.chain_id,
        "at": row.at,
        "actor": row.actor,
        "source": row.source,
        "old_hash": row.old_hash,
        "new_hash": row.new_hash,
        "note": row.note,
    }
