"""Tri-state results, the error code table, and diagnostics (design doc 01 §4, 02 §7/§7.1).

Three layers:
- ``Ok`` / ``Missing`` / ``Failed``: the tri-state of stage evaluation. **Missing is not an
  error**, and **an error is not a value**.
- ``CODES``: the error codes the engine can **actually emit** today -- the single source of truth
  and the reference set for conformance. Codes the spec has defined but that are not implemented
  yet (all of ``E3xxx``, the graph rules ``E11xx``, the ``udf``/``emit`` ones) are **not in this
  table**; they join it as their layer lands.
- ``Diagnostic``: a human-facing diagnostic (code + message + fix + optional allowed values), the
  handle an LLM uses for self-correction.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Final

CODES: Final[dict[str, str]] = {
    # ---- compile time (UP2-E1xxx) ----
    "UP2-E1001": "unknown operator",
    "UP2-E1002": "unknown or reserved action",
    "UP2-E1003": "py function is not in the allowlist",
    "UP2-E1004": "stage length does not match the operator arity",
    "UP2-E1005": "parameter schema validation failed",
    "UP2-E1006": "reference targets an unknown root or a key that cannot be referenced",
    "UP2-E1007": "a literal was written where a reference is required",
    "UP2-E1009": "a step name is reserved or duplicated",
    "UP2-E1010": "udf references an unregistered user-defined function",
    "UP2-E1012": "resource limits exceeded",
    "UP2-E1013": "regex contains nested quantifiers (ReDoS risk)",
    "UP2-E1014": "cross-node reference to a local key prefixed with `_`",
    "UP2-E1015": "ctx.set/del wrote a path outside locals",
    "UP2-E1016": "a `next`/`exit` target is not a step of the story",
    "UP2-E1107": "operator unavailable (optional dependency missing)",
    # ---- runtime (UP2-E2xxx) ----
    "UP2-E2001": "reference path cannot be read at runtime (shallower than declared)",
    "UP2-E2002": "stage input type does not match what the operator expects",
    "UP2-E2003": "export contains a value that cannot be serialized",
    "UP2-E2004": "deferred import of an operator optional dependency failed",
    "UP2-E2005": "value conversion failed",
    "UP2-E2007": "py.parse_time failed to parse",
    "UP2-E2008": "py.parse_time needs natural-language dates but dateparser is not installed",
    "UP2-E2009": "operator returned a value that cannot be a product",
    "UP2-E2012": "the iteration count of `each` exceeds MAX_EACH_ITER",
    # UP2-E2015 ("value is missing and the effective policy is raise") is retired with the
    # settlement policy: a missing value is not an error any more. The number is not reused.
    "UP2-E2016": "sandbox execution over limits (feed time / memory / host round-trip budget)",
    "UP2-E2017": "sandbox code raised an exception (syntax or unsupported constructs)",
    "UP2-E2018": "py.getitem found no such key or index",
    "UP2-E2099": "operator raised an unexpected exception",
}


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """A human-facing diagnostic. ``fix`` must be a fix that can be carried out in one sentence."""

    code: str
    message: str
    fix: str = ""
    pointer: str = ""
    allowed: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.fix:
            payload["fix"] = self.fix
        if self.pointer:
            payload["pointer"] = self.pointer
        if self.allowed:
            payload["allowed"] = list(self.allowed)
        return payload

    def __str__(self) -> str:
        parts = [f"{self.code}: {self.message}"]
        if self.pointer:
            parts.append(f"at {self.pointer}")
        if self.fix:
            parts.append(f"fix: {self.fix}")
        return " | ".join(parts)


def diag(
    code: str,
    message: str,
    /,
    *,
    fix: str = "",
    pointer: str = "",
    allowed: Iterable[str] = (),
) -> Diagnostic:
    """Build a diagnostic, rejecting codes outside the table.

    A misspelled code is a programming error, not a user error.
    """
    if code not in CODES:
        raise ValueError(f"unknown error code {code!r}; declare it in errors.CODES first")
    return Diagnostic(code=code, message=message, fix=fix, pointer=pointer, allowed=tuple(allowed))


class Up2Error(Exception):
    """Exception carrying an error code (used mostly at compile time).

    At runtime everything turns into ``Failed``.
    """

    def __init__(self, diagnostic: Diagnostic) -> None:
        super().__init__(str(diagnostic))
        self.diagnostic = diagnostic


@dataclass(frozen=True, slots=True)
class Ok:
    """A hit."""

    value: Any


@dataclass(frozen=True, slots=True)
class Missing:
    """No hit: the selector did not match, the regex did not match, the key is absent.

    A normal result, not an error.
    """

    reason: str


@dataclass(frozen=True, slots=True)
class Failed:
    """Evaluation failed: type mismatch, conversion failure, missing dependency, and so on."""

    code: str
    reason: str
    fix: str = ""


type Outcome = Ok | Missing | Failed
