"""The `examples/etl/` cases: every one is compiled and run against its committed expected product.

Each directory is `story.json` + `input.txt` + `expected.json`, plus an optional `host.py` that
exports `TYPES` (name → constructor) and/or `UDOFS` (name → callable). A missing optional engine
(`selectolax` for `css` / `css1`, `lxml` for `xpath`) skips that case, exactly like the operator
tests; the release CI installs every extra, so the whole set runs there.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from uniparser2 import register_type, run, unregister_type

EXAMPLES = Path(__file__).resolve().parents[2] / "examples" / "etl"
CASES = tuple(
    sorted(path for path in EXAMPLES.iterdir() if path.is_dir() and (path / "story.json").is_file())
)


def _load_host(case: Path) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """The optional host hooks of one example."""
    path = case / "host.py"
    if not path.is_file():
        return {}, {}
    spec = importlib.util.spec_from_file_location(f"etl_example_{case.name}", path)
    if spec is None or spec.loader is None:  # pragma: no cover - a broken example is a test bug
        raise AssertionError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return getattr(module, "TYPES", {}), getattr(module, "UDOFS", {})


def _require_engines(story: Any) -> None:
    text = json.dumps(story)
    if '"css' in text:
        pytest.importorskip("selectolax")
    if '"xpath' in text:
        pytest.importorskip("lxml")
    if '"json"' in text:
        pytest.importorskip("jmespath")


def test_the_example_set_is_not_empty() -> None:
    assert CASES, f"no example directories under {EXAMPLES}"


@pytest.mark.parametrize("case", CASES, ids=[case.name for case in CASES])
def test_etl_example(case: Path) -> None:
    story = json.loads((case / "story.json").read_text(encoding="utf-8"))
    _require_engines(story)
    expected = json.loads((case / "expected.json").read_text(encoding="utf-8"))
    text = (case / "input.txt").read_text(encoding="utf-8")
    types, udfs = _load_host(case)
    for name, constructor in types.items():
        register_type(name, constructor)
    try:
        product = run(story, input=text, udfs=udfs)
    finally:
        for name in types:
            unregister_type(name)
    assert product == expected


def test_every_example_has_the_three_files() -> None:
    for case in CASES:
        for name in ("story.json", "input.txt", "expected.json"):
            assert (case / name).is_file(), f"{case.name} is missing {name}"
