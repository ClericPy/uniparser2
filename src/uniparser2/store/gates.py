"""The `publish` gates that live above the store (design doc 04 §6).

G1 is not here: the store's ``publish`` compiles the graph before it writes, so it cannot be
skipped. These two functions are the rest of the gate, as pure functions, so a refusal happens
**before** any IO and is testable without a store:

- **G2** the regression of the snapshots that already exist. The runner is `cli/samples.py`
  (``up2 test``, `04` §7-S5), and this module keeps the pure half of the gate: the trace contract
  that makes a bypass auditable -- ``--skip-tests`` without ``--note`` is ``UP2-E3005``, and with a
  note the text travels into the audit row. A regression that fails raises the same ``UP2-E3005``,
  built by the runner so the refusal carries the JSON Pointer difference.
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
