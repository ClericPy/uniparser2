"""Host user-defined function registry (design doc 02 §6.10, Q42).

**This is how "no arbitrary code execution inside the rules" lands**: a chain can only supply a
function name plus parameters, while the function body is registered by the host when the process
starts (``register_udf`` or the ``entry_points`` group ``uniparser2.udfs``). An unregistered name is
reported at **compile time** as ``UP2-E1010`` instead of being discovered halfway through a run.

This module is **pure dictionary operations**: no third-party import, no file read. Entry point
discovery (which reads distribution metadata) lives in ``uniparser2.host``, keeping the "core has no
IO" invariant.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Final

type UdfFn = Callable[..., Any]
"""The user-defined function contract: ``fn(*arguments) -> value``.

A single DTO argument, one explicit argument, or a spread list/mapping depends on the stage; an
awaitable answer is ``UP2-E2009`` because the kernel is synchronous. Any other answer may flow
mid-chain; the run's exit and a `type` stage require JSON.
"""

_UDFS: dict[str, UdfFn] = {}
_ACTIVE: ContextVar[Mapping[str, UdfFn] | None] = ContextVar("uniparser2_active_udfs", default=None)
"""The table a **run** compiled with: the process-wide defaults plus the run's overlay.

It is a context variable rather than a parameter through every compiler call: the `udf` operator
checks a signature at compile time, and a story compiled by `run(udfs=...)` must see the same table
the run will use. A compile outside a run sees the process-wide table.
"""


def register_udf(name: str, fn: UdfFn) -> None:
    """Register (or replace) one user-defined function. ``name`` is what the chain writes."""
    if not name or not callable(fn):
        raise ValueError(f"register_udf needs a non-empty name and a callable, got {name!r}")
    _UDFS[name] = fn


def unregister_udf(name: str) -> bool:
    """Remove one user-defined function; return whether it was really removed."""
    return _UDFS.pop(name, None) is not None


def get_udf(name: str) -> UdfFn | None:
    """Get a user-defined function by name (the run's table first, then the process-wide one)."""
    active = _ACTIVE.get()
    if active is not None and name in active:
        return active[name]
    return _UDFS.get(name)


def udf_names() -> tuple[str, ...]:
    """The registered function names (the run's table wins, sorted)."""
    active = _ACTIVE.get()
    if active is not None:
        return tuple(sorted(active))
    return tuple(sorted(_UDFS))


def all_udfs() -> dict[str, UdfFn]:
    """A copy of the process-wide table, for a run to merge its overlay over."""
    return dict(_UDFS)


@contextmanager
def use_udfs(table: Mapping[str, UdfFn]) -> Iterator[None]:
    """Make ``table`` the visible table for the duration of a compile (a run's own overlay)."""
    token = _ACTIVE.set(table)
    try:
        yield
    finally:
        _ACTIVE.reset(token)


UNREGISTERED_FIX: Final = (
    "call register_udf(name, function) in the host, or pass udfs={...} to run()"
)
