"""The committed catalogue snapshot: rendering it is part of the suite.

``docs/report/up2-report.md`` is generated from a real run, so it can go stale like any generated
artifact. This module makes that a test instead of a workflow step:

- by default it **compares** a fresh render with the committed file, so a stale catalogue fails
  locally and in CI;
- with ``UP2_UPDATE_REPORT=1`` it **rewrites** the file instead, which is the local way to
  refresh it (`UP2_UPDATE_REPORT=1 uv run pytest tests/report`).

The render depends on the optional engines (a missing one changes that operator's cases), so the
whole module skips unless every engine the catalogue touches is importable — the cells that install
all extras are the ones that really check it.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from collections.abc import Iterable
from pathlib import Path
from types import ModuleType

import pytest

from uniparser2.core import registry

UPDATE_ENV = "UP2_UPDATE_REPORT"
"""Set it to rewrite the catalogue instead of asserting on it."""

_ROOT = Path(__file__).resolve().parents[2]
CATALOGUE = _ROOT / "docs" / "report" / "up2-report.md"


def _load_report_tool() -> ModuleType:
    """Import ``tools/demo_report.py`` by path, once per process.

    It lives outside the package on purpose (a development tool, not shipped), and the type checkers
    infer ``src/`` as the import root, so a plain ``import tools.demo_report`` is not resolvable.
    The module name is shared with ``test_rendering`` so both modules read the tool's cached case
    run (``_collect``).
    """
    existing = sys.modules.get("demo_report")
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location("demo_report", _ROOT / "tools" / "demo_report.py")
    assert spec is not None and spec.loader is not None  # the file is in this repository
    module = importlib.util.module_from_spec(spec)
    sys.modules["demo_report"] = module
    spec.loader.exec_module(module)
    return module


demo_report = _load_report_tool()


def required_engines() -> tuple[str, ...]:
    """Every optional engine a case touches (operator-level and action-level declarations)."""
    names: set[str] = set()
    for item in registry.report():
        names.update(item.requires)
        for action in item.actions:
            names.update(action.requires)
    return tuple(sorted(names))


def missing_engines(names: Iterable[str]) -> tuple[str, ...]:
    return tuple(name for name in names if importlib.util.find_spec(name) is None)


_MISSING = missing_engines(required_engines())

pytestmark = pytest.mark.skipif(
    bool(_MISSING),
    reason=f"the catalogue needs every optional engine; missing: {', '.join(_MISSING)}",
)


def test_the_probe_covers_the_engines_the_render_needs() -> None:
    """The skip decision must be based on the engines the cases really use."""
    engines = required_engines()
    assert "selectolax" in engines  # css / css1
    assert "lxml" in engines  # xpath
    assert "pydantic_monty" in engines  # code
    assert missing_engines(("definitely_not_installed_xyz",)) == ("definitely_not_installed_xyz",)


def test_catalogue_matches_a_fresh_render() -> None:
    rendered = demo_report.build_md()
    if os.environ.get(UPDATE_ENV):
        CATALOGUE.write_text(rendered, encoding="utf-8", newline="\n")
        return
    assert CATALOGUE.is_file(), (
        f"{CATALOGUE} is missing; run `{UPDATE_ENV}=1 uv run pytest tests/report`"
    )
    committed = CATALOGUE.read_text(encoding="utf-8")
    assert committed == rendered, (
        "the committed catalogue is stale: run "
        f"`{UPDATE_ENV}=1 uv run pytest tests/report` to refresh it"
    )
