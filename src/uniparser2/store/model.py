"""The storage layer's data model (design doc 04 §2, §2.1).

One row per chain -- ``(root_domain, tpl_key)`` is unique -- plus an append-only audit row that
keeps **fingerprints only**. There is deliberately no ``dsl_version``: the dialect of a stored chain
is checked by the compiler, not by a stored number (`04` §3, `D-04-3`).

The layering rule (`01` §1) puts this package beside ``cli/`` as the only layer allowed to touch
disk; it depends on ``core``'s public interface and never the other way round.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from uniparser2.core.values import JsonValue

type Status = Literal["draft", "ready", "disabled"]
"""The lifecycle of a chain: ``draft`` / ``ready`` / ``disabled`` (`04` §2)."""

type Source = Literal["human", "agent", "import"]
"""Who wrote it: ``human`` / ``agent`` / ``import`` (`04` §2, `D-04-2`)."""

type Graph = dict[str, JsonValue] | list[JsonValue]
"""The chain data of `03` §2: a story bundle (a JSON object with ``globals`` / ``nodes``) or a
field chain."""


@dataclass(frozen=True, slots=True)
class Template:
    """One stored chain (`04` §2). ``graph`` is **data**, never a compilation product."""

    chain_id: str
    root_domain: str
    tpl_key: str
    status: Status
    source: Source
    graph: Graph
    create_time: str
    update_time: str


@dataclass(frozen=True, slots=True)
class TemplateMeta:
    """A listing entry: everything of a `Template` except the graph (`04` §4)."""

    chain_id: str
    root_domain: str
    tpl_key: str
    status: Status
    source: Source
    create_time: str
    update_time: str


@dataclass(frozen=True, slots=True)
class AuditRow:
    """One change of one chain (`04` §2.1). ``old_hash`` is ``None`` on the first write."""

    seq: int
    chain_id: str
    at: str
    actor: str
    source: Source
    old_hash: str | None
    new_hash: str
    note: str | None = None


@dataclass(frozen=True, slots=True)
class PublishResult:
    """What a `publish` did (`04` §4).

    ``changed`` is ``False`` when the fingerprint was already the stored one -- in that case nothing
    is written at all and ``audit_seq`` is ``None`` (`04` §5 step 3).
    """

    chain_id: str
    old_hash: str | None
    new_hash: str
    changed: bool
    audit_seq: int | None


def meta_of(template: Template) -> TemplateMeta:
    """Drop the graph: a listing entry is metadata (`04` §4)."""
    return TemplateMeta(
        chain_id=template.chain_id,
        root_domain=template.root_domain,
        tpl_key=template.tpl_key,
        status=template.status,
        source=template.source,
        create_time=template.create_time,
        update_time=template.update_time,
    )


def new_chain_id() -> str:
    """The single place a chain identity is generated (`04` §2): 32 hex characters, no dashes.

    Switching to ULID later touches this function alone.
    """
    return uuid.uuid4().hex


def utc_now() -> str:
    """The timestamp every ``create_time`` / ``update_time`` / audit ``at`` is written with.

    ISO 8601 in UTC, with the ``+00:00`` offset (`04` §2). One function, so a test can fix the
    clock.
    """
    return datetime.now(UTC).isoformat()
