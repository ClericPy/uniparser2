"""The `publish` gates that live above the store (design doc 04 §6).

G1 is not here: the store's ``publish`` compiles the graph before it writes, so it cannot be
skipped. These two functions are the rest of the gate, as pure functions, so a refusal happens
**before** any IO and is testable without a store:

- **G2** the regression of the snapshots that already exist. The runner itself belongs to the SOP
  slice (``up2 test``, `04` §7-S5), so what this slice enforces is the trace contract that makes the
  bypass auditable: ``--skip-tests`` without ``--note`` is ``UP2-E3005``, and with a note the text
  travels into the audit row. Until the runner lands, a publish without ``--skip-tests`` regresses
  the snapshots that exist -- an empty set -- and the runner raises the same ``UP2-E3005`` for a
  mismatch.
- **G3** overwriting a row whose ``status`` is ``ready`` needs ``--confirm-overwrite``. `04` §5.1
  assigns that refusal no code, so it is a usage message and the CLI exits ``2``.
"""

from __future__ import annotations

from typing import Final

from uniparser2.core.errors import Diagnostic, diag

from .model import Status

READY: Final[Status] = "ready"


def gate_skip_tests(*, skip_tests: bool, note: str | None) -> Diagnostic | None:
    """G2: ``--skip-tests`` must leave a trace, so it needs ``--note`` (`04` §6)."""
    if skip_tests and not note:
        return diag(
            "UP2-E3005",
            "`--skip-tests` was given without `--note`",
            fix="run the snapshot regression, or record why it is skipped with `--note`",
        )
    return None


def gate_overwrite(status: Status | None, *, confirm: bool) -> str | None:
    """G3: replacing a ``ready`` chain is an explicit decision (`04` §6)."""
    if status == READY and not confirm:
        return (
            "the stored chain has status 'ready': pass --confirm-overwrite to replace it, "
            "or set the row back to 'draft' first"
        )
    return None
