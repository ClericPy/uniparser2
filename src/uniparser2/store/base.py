"""The ``TemplateStore`` protocol and the write algorithm every store runs (design doc 04 §4, §5).

The protocol is a ``Protocol`` rather than a base class on purpose: a host injects its own
implementation (MySQL, for instance), the kernel imports no concrete store, and ``cli`` picks the
implementation from configuration (`04` §4).

The fixed steps of ``publish`` (`04` §5) live **once**, in :func:`publish_into`, over the small
:class:`StoreBackend` seam: validate → compile (G1, never skippable) → read the old row and
recompile what was read back → no-op when the fingerprint is unchanged → write the row → append
exactly one audit row → commit → verify the row that was written. A store therefore implements
storage, and the semantics of a write are identical in both stores by construction.
"""

from __future__ import annotations

import builtins
import re
from collections.abc import Iterable, Mapping
from contextlib import AbstractContextManager
from typing import Final, Protocol

from uniparser2.core.compile import compile_field
from uniparser2.core.errors import Diagnostic, Up2Error, diag
from uniparser2.core.story import compile_story

from .fingerprint import graph_hash
from .model import (
    AuditRow,
    Graph,
    PublishResult,
    Source,
    Status,
    Template,
    TemplateMeta,
    new_chain_id,
    utc_now,
)

STORY_KEY: Final = "steps"
"""A chain file carrying ``steps`` is a story bundle; anything else is a field chain (`03` §2)."""

TPL_KEY_RULE: Final = r"^[\w\u4e00-\u9fff][\w\u4e00-\u9fff.-]{0,63}$"
"""The character set of ``tpl_key`` (`04` §2). ``FileStore`` uses the key as a file name."""

_TPL_KEY_PATTERN: Final = re.compile(TPL_KEY_RULE)
_DEFAULT_STATUS: Final[Status] = "draft"


class TemplateStore(Protocol):
    """Where a frozen chain lives (`04` §4).

    ``get`` answers the complete ``Template`` -- the graph is **data**, so no ``compile()`` happens
    here and the store holds no engine state. ``list`` answers metadata without the graph.
    ``publish`` is the **only write entry point**. ``audit`` answers the rows of one chain in
    ascending ``seq`` order.
    """

    def get(self, root_domain: str, tpl_key: str) -> Template | None:
        """The stored chain, or ``None``. Performs no ``compile()``."""
        ...

    def list(
        self, *, root_domain: str | None = None, status: Status | None = None
    ) -> builtins.list[TemplateMeta]:
        """Listing entries (no graph), filtered by the two optional keys."""
        ...

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
        """The only write entry point: gates, then the row and its audit row, atomically."""
        ...

    def audit(self, chain_id: str) -> builtins.list[AuditRow]:
        """The change history of one chain, oldest first."""
        ...


class Transaction(Protocol):
    """The two writes of one publish, inside whatever atomicity the store has (`04` §5 step 6)."""

    def write_template(self, template: Template) -> None:
        """Insert the row, or update it in place."""
        ...

    def append_audit(
        self,
        template: Template,
        *,
        actor: str,
        old_hash: str | None,
        new_hash: str,
        note: str | None,
    ) -> int:
        """Append the audit row of this write and answer its assigned ``seq``."""
        ...


class StoreBackend(Protocol):
    """The storage seam :func:`publish_into` writes through (not the injection point; see above)."""

    def read_template(self, root_domain: str, tpl_key: str) -> Template | None:
        """Read one row; the caller recompiles its graph before trusting it (`01` §8)."""
        ...

    def transaction(self) -> AbstractContextManager[Transaction]:
        """Open the write scope: SQLite opens one ``BEGIN IMMEDIATE``; the file store has none."""
        ...


def lint_graph(graph: Graph) -> None:
    """Compile a graph, discarding the product: G1 of `04` §6, mandatory and not skippable.

    A story bundle is compiled with the story layer, a field chain with the operator layer; both
    raise ``Up2Error`` with a ``UP2-E1xxx`` code when the chain is bad.
    """
    if isinstance(graph, Mapping) and STORY_KEY in graph:
        compile_story(graph)
    else:
        compile_field(graph, products=())


def publish_into(
    backend: StoreBackend,
    graph: Graph,
    *,
    root_domain: str,
    tpl_key: str,
    actor: str,
    source: Source,
    note: str | None = None,
) -> PublishResult:
    """The fixed steps of `04` §5, shared by both stores."""
    _check_identity(root_domain=root_domain, tpl_key=tpl_key)
    lint_graph(graph)
    new_hash = graph_hash(graph)
    old = _read(backend, root_domain, tpl_key)
    old_hash: str | None = None
    if old is not None:
        # An already existing chain is recompiled too, so a read-back path cannot be bypassed
        # (`04` §5): a stored graph that no longer compiles is reported instead of overwritten.
        lint_graph(old.graph)
        old_hash = graph_hash(old.graph)
        if old_hash == new_hash:
            return PublishResult(
                chain_id=old.chain_id,
                old_hash=old_hash,
                new_hash=new_hash,
                changed=False,
                audit_seq=None,
            )
    now = utc_now()
    template = Template(
        chain_id=old.chain_id if old is not None else new_chain_id(),
        root_domain=root_domain,
        tpl_key=tpl_key,
        status=old.status if old is not None else _DEFAULT_STATUS,
        source=source,
        graph=graph,
        create_time=old.create_time if old is not None else now,
        update_time=now,
    )
    audit_seq = _write(
        backend, template, actor=actor, old_hash=old_hash, new_hash=new_hash, note=note
    )
    _verify_readback(backend, template, new_hash)
    return PublishResult(
        chain_id=template.chain_id,
        old_hash=old_hash,
        new_hash=new_hash,
        changed=True,
        audit_seq=audit_seq,
    )


def chain_without_audit(chain_id: str) -> Diagnostic:
    """One half of `UP2-E3003`, repaired by :func:`repair_chain` (`04` §5.1, §10)."""
    return diag(
        "UP2-E3003",
        f"the chain {chain_id} has no audit row",
        fix="re-publish the chain so its audit row is appended, or run `up2 doctor --fix`",
        chain_id=chain_id,
    )


def audit_without_chain(chain_id: str) -> Diagnostic:
    """The other half of `UP2-E3003`: an audit row outlives its template row (`04` §4.2)."""
    return diag(
        "UP2-E3003",
        f"the audit row of {chain_id} has no chain",
        fix="this chain was deleted outside the store; archive or remove its audit file",
        chain_id=chain_id,
    )


class DoctorBackend(Protocol):
    """The store surface `up2 doctor --fix` needs to write the audit row a chain is missing.

    Only the two things a repair is made of: find the row its ``chain_id`` names, and append one
    audit row through the store's own write scope (`04` §5 step 6) -- so a repair runs inside the
    same atomicity a publish does.
    """

    def find_chain(self, chain_id: str) -> Template | None:
        """The row one ``chain_id`` names, so a repair can write beside it (`04` §10)."""
        ...

    def transaction(self) -> AbstractContextManager[Transaction]:
        """The write scope of one repair: SQLite opens its own, the file store has none."""
        ...


def repair_chain(
    backend: DoctorBackend, chain_id: str, *, actor: str, note: str
) -> AuditRow | None:
    """`up2 doctor --fix`: write the audit row of a chain that has none (`04` §7.1, §10).

    ``old_hash`` is ``None`` and ``new_hash`` is the fingerprint of the **stored** graph: the row
    says "this chain exists as this graph and had no audit row", which is exactly the finding. The
    ``actor`` and ``note`` the CLI passes are what mark the row as synthesized, because `04` §2.1
    gives the audit row nowhere else to say it. ``None`` means there is nothing to repair: the
    ``chain_id`` a finding named has no row in this store.
    """
    template = backend.find_chain(chain_id)
    if template is None:
        return None
    new_hash = graph_hash(template.graph)
    with backend.transaction() as tx:
        seq = tx.append_audit(template, actor=actor, old_hash=None, new_hash=new_hash, note=note)
    return AuditRow(
        seq=seq,
        chain_id=chain_id,
        at=utc_now(),
        actor=actor,
        source=template.source,
        old_hash=None,
        new_hash=new_hash,
        note=note,
    )


def _check_identity(*, root_domain: str, tpl_key: str) -> None:
    """Step 1 of `04` §5: nothing is written when the identity itself is unusable."""
    if not root_domain:
        raise Up2Error(
            diag(
                "UP2-E3002",
                "`root_domain` is empty",
                fix="name the site the chain is bound to, for example `ah.gov.cn` or `local`",
            )
        )
    if _TPL_KEY_PATTERN.fullmatch(tpl_key) is None:
        raise Up2Error(
            diag(
                "UP2-E3002",
                f"`tpl_key` {tpl_key!r} does not match {TPL_KEY_RULE}",
                fix=(
                    "letters, digits, underscores, Chinese characters, dots and hyphens, at most "
                    "64 characters, not starting with a dot or a hyphen"
                ),
            )
        )


def _read(backend: StoreBackend, root_domain: str, tpl_key: str) -> Template | None:
    """A read that cannot happen is a store failure, not a missing chain (`04` §5.1 E3004)."""
    try:
        return backend.read_template(root_domain, tpl_key)
    except Exception as exc:
        raise _store_failed(root_domain, tpl_key, exc) from exc


def _write(
    backend: StoreBackend,
    template: Template,
    *,
    actor: str,
    old_hash: str | None,
    new_hash: str,
    note: str | None,
) -> int:
    """Steps 4-6 of `04` §5: the row, exactly one audit row, and the commit."""
    try:
        with backend.transaction() as tx:
            tx.write_template(template)
            return tx.append_audit(
                template,
                actor=actor,
                old_hash=old_hash,
                new_hash=new_hash,
                note=note,
            )
    except Exception as exc:
        raise _store_failed(template.root_domain, template.tpl_key, exc) from exc


def _verify_readback(backend: StoreBackend, template: Template, new_hash: str) -> None:
    """`UP2-E3001`: what was written back must be the graph that was meant (`04` §5.1)."""
    stored = _read(backend, template.root_domain, template.tpl_key)
    if stored is None or graph_hash(stored.graph) != new_hash:
        raise Up2Error(
            diag(
                "UP2-E3001",
                f"the graph written under {template.root_domain}/{template.tpl_key} does not match "
                f"the expected fingerprint {new_hash}",
                fix="run `up2 get` again and compare; make sure there is no concurrent writer",
            )
        )


def _store_failed(root_domain: str, tpl_key: str, exc: Exception) -> Up2Error:
    """`UP2-E3004`: permissions, disk, a SQLite lock, a missing directory (`04` §5.1)."""
    return Up2Error(
        diag(
            "UP2-E3004",
            f"cannot reach {root_domain}/{tpl_key}: {type(exc).__name__}: {exc}",
            fix="check the store path, its permissions and the free space, then publish again",
        )
    )


def select_entries(
    entries: Iterable[TemplateMeta],
    *,
    root_domain: str | None = None,
    status: Status | None = None,
) -> list[TemplateMeta]:
    """Filter and order listing entries the same way in both stores (`04` §4)."""
    kept = [
        entry
        for entry in entries
        if (root_domain is None or entry.root_domain == root_domain)
        and (status is None or entry.status == status)
    ]
    return sorted(kept, key=lambda entry: (entry.root_domain, entry.tpl_key))
