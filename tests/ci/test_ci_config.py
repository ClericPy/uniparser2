"""Workflow options are checked against ``pyproject.toml`` before CI runs.

The ``--extra time`` CI failure happened because an extra was removed from ``pyproject.toml`` while
the workflow kept the old name. A missing extra is a configuration typo, so it is cheap to catch
locally: one test reads both files and compares the names.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = ROOT / ".github" / "workflows"
_EXTRA_FLAG = re.compile(r"--extra(?:=|\s+)([A-Za-z0-9_-]+)")


def test_every_extra_the_workflows_ask_for_is_declared() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    declared = set(project["project"].get("optional-dependencies", {}))
    used: set[str] = set()
    for path in sorted(WORKFLOW_DIR.glob("*.yml")):
        used |= set(_EXTRA_FLAG.findall(path.read_text(encoding="utf-8")))
    assert used, "the CI workflows do not ask for any extra"
    assert used <= declared, f"CI asks for undeclared extras: {sorted(used - declared)}"
