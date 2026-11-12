"""The walkthrough demo is executable: a stale example fails here, not silently at the user.

``demo.py`` is a hand-maintained cheat-sheet, so it rots the way documentation rots. Running it as
a subprocess is the cheapest honest check: an example that no longer compiles exits non-zero, while
a missing optional engine only skips its own chain (``UP2-E1107``) and is allowed.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]


def test_the_demo_runs_to_completion() -> None:
    # The command is two repository paths, never caller input.
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(_ROOT / "demo.py")],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
        check=False,
    )
    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined[-4000:]
    assert "operators exercised:" in result.stdout
    assert "Traceback" not in combined
