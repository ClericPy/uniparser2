"""``FileStore``: one file per chain plus an append-only audit line file (design doc 04 §4.1).

::

    $UP2_HOME/
      chains/<root_domain>/<tpl_key>.json     # the complete Template
      audit/<root_domain>/<tpl_key>.jsonl     # append-only, one audit row per line

Applicability: local development, the trial UI, a single-machine SOP flow. A chain file is written
to a temporary file in its own directory and then moved into place with ``os.replace``, so a reader
never sees a half-written chain, and the canonical key order keeps a version-control diff readable.

**Single-writer assumption**: there is no cross-process lock. Concurrent writers must use
``SqliteStore`` (`04` §4.1). ``UP2-E3001``'s read-back check is the only guard, and it is
best-effort.

``audit()`` is keyed by ``chain_id`` while the layout is keyed by ``(root_domain, tpl_key)``, so it
scans the audit tree and filters by ``chain_id``. That keeps the designed layout, keeps the audit
row shape of `04` §2.1, and keeps an audit row reachable after its template row is gone -- the
reason `04` §4.2 refuses a foreign key. Consistent with `04` §5 step 6, the chain file lands
**before** the audit line is appended, so a crash between the two leaves "a chain without an audit
row", which :meth:`inconsistencies` reports as ``UP2-E3003``.
"""

from __future__ import annotations

import builtins
import contextlib
import json
import os
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any, Final

from uniparser2.core.errors import Diagnostic

from .base import (
    Transaction,
    audit_without_chain,
    chain_without_audit,
    publish_into,
    select_entries,
)
from .model import AuditRow, Graph, PublishResult, Source, Status, Template, TemplateMeta, meta_of

CHAINS_DIR: Final = "chains"
AUDIT_DIR: Final = "audit"
AUDIT_SUFFIX: Final = ".jsonl"
CHAIN_SUFFIX: Final = ".json"


class FileStore:
    """A `TemplateStore` on the filesystem (`04` §4.1)."""

    def __init__(self, home: Path) -> None:
        """Remember where the store lives; the constructor touches no filesystem (`04` §4.1)."""
        self.home = Path(home)

    def get(self, root_domain: str, tpl_key: str) -> Template | None:
        """The stored chain, or ``None``. Performs no ``compile()`` (`04` §4)."""
        path = self.chain_path(root_domain, tpl_key)
        if not path.is_file():
            return None
        return _template_from_json(_load_json(path))

    def list(
        self, *, root_domain: str | None = None, status: Status | None = None
    ) -> builtins.list[TemplateMeta]:
        """Listing entries, filtered and ordered (`04` §4)."""
        metas = (meta_of(_template_from_json(_load_json(path))) for path in self._chain_files())
        return select_entries(metas, root_domain=root_domain, status=status)

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
        """The only write entry point; the steps are `04` §5."""
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
        """The change history of one chain, oldest first (`04` §4)."""
        rows = [row for row in self._audit_files_rows() if row.chain_id == chain_id]
        return sorted(rows, key=lambda row: row.seq)

    def inconsistencies(self) -> builtins.list[Diagnostic]:
        """The `UP2-E3003` findings (`04` §5.1, §10); the repair is the later `doctor` slice."""
        chains = self._chain_ids()
        audited = {row.chain_id for row in self._audit_files_rows()}
        return [chain_without_audit(chain_id) for chain_id in sorted(chains - audited)] + [
            audit_without_chain(chain_id) for chain_id in sorted(audited - chains)
        ]

    def chain_path(self, root_domain: str, tpl_key: str) -> Path:
        """Where one chain's ``Template`` JSON lives (`04` §4.1)."""
        return self.home / CHAINS_DIR / root_domain / f"{tpl_key}{CHAIN_SUFFIX}"

    def audit_path(self, root_domain: str, tpl_key: str) -> Path:
        """Where one chain's audit lines live (`04` §4.1)."""
        return self.home / AUDIT_DIR / root_domain / f"{tpl_key}{AUDIT_SUFFIX}"

    # -- the StoreBackend seam (04 §5) ---------------------------------------------------------

    def read_template(self, root_domain: str, tpl_key: str) -> Template | None:
        """The same read as ``get``; named after the seam `04` §5 writes through."""
        return self.get(root_domain, tpl_key)

    @contextmanager
    def transaction(self) -> Iterator[Transaction]:
        """No transaction: the chain file is landed first and the audit line appended after.

        That order is `04` §5 step 6's file-store rule: a crash in between leaves a chain without an
        audit row (``UP2-E3003``), never an audit row without a chain.
        """
        yield self

    def write_template(self, template: Template) -> None:
        """Atomically replace the chain file: temporary file, then ``os.replace``."""
        path = self.chain_path(template.root_domain, template.tpl_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(asdict(template), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        handle, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        os.close(handle)
        temporary = Path(name)
        try:
            temporary.write_text(text, encoding="utf-8", newline="\n")
            os.replace(temporary, path)
        except OSError:
            with contextlib.suppress(OSError):
                temporary.unlink()
            raise

    def append_audit(
        self,
        template: Template,
        *,
        actor: str,
        old_hash: str | None,
        new_hash: str,
        note: str | None,
    ) -> int:
        """Append one line; its ``seq`` is the line number within this chain's audit file."""
        path = self.audit_path(template.root_domain, template.tpl_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        row = AuditRow(
            seq=_line_count(path) + 1,
            chain_id=template.chain_id,
            at=template.update_time,
            actor=actor,
            source=template.source,
            old_hash=old_hash,
            new_hash=new_hash,
            note=note,
        )
        line = json.dumps(asdict(row), sort_keys=True, ensure_ascii=False) + "\n"
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(line)
        return row.seq

    # -- internals -----------------------------------------------------------------------------

    def _chain_files(self) -> builtins.list[Path]:
        root = self.home / CHAINS_DIR
        return sorted(root.rglob(f"*{CHAIN_SUFFIX}")) if root.is_dir() else []

    def _audit_files(self) -> builtins.list[Path]:
        root = self.home / AUDIT_DIR
        return sorted(root.rglob(f"*{AUDIT_SUFFIX}")) if root.is_dir() else []

    def _audit_files_rows(self) -> Iterator[AuditRow]:
        for path in self._audit_files():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    yield _audit_from_json(json.loads(line))

    def _chain_ids(self) -> set[str]:
        return {_template_from_json(_load_json(path)).chain_id for path in self._chain_files()}


def _load_json(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def _template_from_json(data: Mapping[str, Any]) -> Template:
    """Read a chain file back as **data** (`01` §8); nothing here is a compilation product."""
    return Template(
        chain_id=data["chain_id"],
        root_domain=data["root_domain"],
        tpl_key=data["tpl_key"],
        status=data["status"],
        source=data["source"],
        graph=data["graph"],
        create_time=data["create_time"],
        update_time=data["update_time"],
    )


def _audit_from_json(data: Mapping[str, Any]) -> AuditRow:
    return AuditRow(
        seq=data["seq"],
        chain_id=data["chain_id"],
        at=data["at"],
        actor=data["actor"],
        source=data["source"],
        old_hash=data["old_hash"],
        new_hash=data["new_hash"],
        note=data.get("note"),
    )


def _line_count(path: Path) -> int:
    if not path.is_file():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
