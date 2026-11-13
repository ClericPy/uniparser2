"""Every chain example the user-facing docs write must compile.

The `type` defect shipped because each operator's tests agreed with a stale doc sentence and
nothing executed the doc's own examples. The report catalogue (`docs/report/`) runs one canonical
chain per action, and `up2 conformance` covers every declared pair; what neither layer sees is a
chain written **in prose** that the engine does not take. This module extracts the inline
``["op", …]`` spans from the README and the operator reference and compiles each one against the
live registry, so a documented spelling that drifted from the schema turns red here. Documented
compile-time refusals are pinned where they belong — `tests/ops` and `tests/compile` — not here.

Chains whose stages include ``node`` are skipped: a standalone `["node", name]` needs a story's
node table, and their shape is what `tests/compile` (lint L5/L6) already asserts.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Final

import pytest

from uniparser2 import Up2Error, compile_field
from uniparser2.core import registry

_ROOT: Final = Path(__file__).resolve().parents[2]

_FILES: Final = (
    _ROOT / "docs" / "operator-reference.md",
    _ROOT / "README.md",
    _ROOT / "README.zh-CN.md",
)

_SPAN: Final = re.compile(r"`([^`\n]+)`")


def _is_stage(item: Any, operators: frozenset[str]) -> bool:
    """Whether a JSON value looks like one stage: ``["op", …]`` with a declared operator name."""
    return isinstance(item, list) and bool(item) and isinstance(item[0], str) and item[0] in operators


def _candidate_spans() -> dict[str, str]:
    """Every inline span that parses as JSON and looks like a chain: text -> first file naming it."""
    operators = frozenset(item.name for item in registry.report())
    found: dict[str, str] = {}
    for path in _FILES:
        for span in _SPAN.findall(path.read_text(encoding="utf-8")):
            span = span.strip()
            if not (span.startswith("[") and span.endswith("]")):
                continue
            try:
                value = json.loads(span)
            except ValueError:
                continue  # prose placeholders (`["udf", f, "**"]`) are not JSON
            stages = value if isinstance(value, list) and value and isinstance(value[0], list) else [value]
            if not (
                isinstance(value, list)
                and value
                and all(_is_stage(stage, operators) for stage in stages)
            ):
                continue
            if any(stage[0] == "node" for stage in stages):
                continue  # needs a story's node table; `tests/compile` owns the shape
            found.setdefault(span, path.name)
    return found


@pytest.mark.parametrize(("chain", "source"), sorted(_candidate_spans().items()))
def test_the_documented_chain_compiles(chain: str, source: str) -> None:
    _compile_documented(json.loads(chain))


def _compile_documented(chain: list[Any]) -> None:
    """Compile one documented chain; a missing optional dependency skips, anything else fails.

    CI installs no extras (`05` §4): a documented `code` chain cannot compile there, and that is
    the environment, not a doc defect — the same convention `tests/report` follows. The chain is
    really compiled where the extra is installed, so the skip names the dependency.
    """
    try:
        compile_field(chain)  # must not raise: the doc writes a chain the engine takes
    except Up2Error as exc:
        if exc.diagnostic.code == "UP2-E1107":
            pytest.skip(f"optional dependency not installed here ({exc.diagnostic.message})")
        raise  # any other code is a doc bug: the doc writes a chain the engine does not take


def test_a_missing_optional_dependency_skips_not_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """The CI-parity guard: an uninstalled optional dependency must skip, never fail.

    This exact shape broke CI once: `["code", …]` compiles where the `[code]` extra is installed
    and raises `UP2-E1107` where it is not, and the difference is the environment, not the doc.
    """
    monkeypatch.setattr(registry, "action_missing_deps", lambda *args, **kwargs: ["pydantic_monty"])
    with pytest.raises(pytest.skip.Exception):
        _compile_documented(json.loads('["code", "len(obj) * 2"]'))


def test_the_extractor_still_sees_the_documented_chains() -> None:
    """A layout or wording change that silences the extractor must fail loudly, not pass vacuously."""
    assert len(_candidate_spans()) >= 30, (
        "the docs' inline chain examples are no longer being extracted; check the files and the span"
        " pattern"
    )
