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

from collections.abc import Callable
from typing import Any, Final

type UdfFn = Callable[..., Any]
"""The user-defined function contract: ``fn(value, **params) -> JSON value``.

Returning a non-JSON value is ``UP2-E2009``.
"""

_UDFS: dict[str, UdfFn] = {}


def register_udf(name: str, fn: UdfFn) -> None:
    """Register (or replace) one user-defined function. ``name`` is what the chain writes."""
    if not name or not callable(fn):
        raise ValueError(f"register_udf needs a non-empty name and a callable, got {name!r}")
    _UDFS[name] = fn


def unregister_udf(name: str) -> bool:
    """Remove one user-defined function; return whether it was really removed."""
    return _UDFS.pop(name, None) is not None


def get_udf(name: str) -> UdfFn | None:
    """Get a user-defined function by name."""
    return _UDFS.get(name)


def udf_names() -> tuple[str, ...]:
    """The registered function names (sorted)."""
    return tuple(sorted(_UDFS))


UNREGISTERED_FIX: Final = (
    "call register_udf(name, function) in the host, or declare an entry point "
    "(group uniparser2.udfs)"
)
