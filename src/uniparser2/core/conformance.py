"""The **pure** part of the conformance audit (design doc 05 §4.1).

This module only does set arithmetic and never touches the filesystem -- scanning test files for
``covers`` markers and error code literals happens in ``uniparser2.cli.conformance`` (IO is only
allowed outside core, invariant I1 of 01 §1.1).

Two kinds of conformance are audited:
- **Coverage**: every ``(operator, action)`` declared in the registry has a case; every implemented
  error code has a case.
- **Orphans**: a case mentions something the registry/code table does not have (a "false green" left
  behind after an operator is deleted or a code is misspelled).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from . import registry
from .errors import CODES


@dataclass(frozen=True, slots=True)
class ConformanceReport:
    """The result of one conformance audit. Acceptance passes only when ``ok`` is true."""

    missing_pairs: tuple[tuple[str, str], ...]
    orphan_pairs: tuple[tuple[str, str], ...]
    missing_codes: tuple[str, ...]
    orphan_codes: tuple[str, ...]
    covered_pairs: int
    declared_pairs: int

    @property
    def ok(self) -> bool:
        return not (
            self.missing_pairs or self.orphan_pairs or self.missing_codes or self.orphan_codes
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "declared_pairs": self.declared_pairs,
            "covered_pairs": self.covered_pairs,
            "missing_pairs": [f"{op}.{action}" for op, action in self.missing_pairs],
            "orphan_pairs": [f"{op}.{action}" for op, action in self.orphan_pairs],
            "missing_codes": list(self.missing_codes),
            "orphan_codes": list(self.orphan_codes),
        }

    def render(self) -> str:
        """The human-facing report (used directly by the CLI)."""
        lines = [
            f"Declaration (operator, action): {self.declared_pairs} pairs, "
            f"covered by cases: {self.covered_pairs} pairs",
            f"error codes implemented: {len(CODES)}",
        ]
        if self.missing_pairs:
            lines.append("uncovered (operator, action):")
            lines += [f"  - {op}.{action}" for op, action in self.missing_pairs]
        if self.orphan_pairs:
            lines.append("orphan cases (not in the registry):")
            lines += [f"  - {op}.{action}" for op, action in self.orphan_pairs]
        if self.missing_codes:
            lines.append("error codes without cases: " + ", ".join(self.missing_codes))
        if self.orphan_codes:
            lines.append(
                "orphan error codes (not in the code table): " + ", ".join(self.orphan_codes)
            )
        lines.append("PASS" if self.ok else "FAIL")
        return "\n".join(lines)


def check(
    *,
    covered_pairs: Iterable[tuple[str, str]],
    covered_codes: Iterable[str],
    declared_pairs: Iterable[tuple[str, str]] | None = None,
    declared_codes: Iterable[str] | None = None,
) -> ConformanceReport:
    """Compare the declarations against the coverage.

    The two ``declared`` parameters exist only as injection points for tests; by default they come
    from the registry and the code table.
    """
    declared_pair_set = frozenset(
        registry.declared_pairs() if declared_pairs is None else declared_pairs
    )
    declared_code_set = frozenset(CODES if declared_codes is None else declared_codes)
    covered_pair_set = frozenset(covered_pairs)
    covered_code_set = frozenset(covered_codes)
    return ConformanceReport(
        missing_pairs=tuple(sorted(declared_pair_set - covered_pair_set)),
        orphan_pairs=tuple(sorted(covered_pair_set - declared_pair_set)),
        missing_codes=tuple(sorted(declared_code_set - covered_code_set)),
        orphan_codes=tuple(sorted(covered_code_set - declared_code_set)),
        covered_pairs=len(covered_pair_set & declared_pair_set),
        declared_pairs=len(declared_pair_set),
    )
