"""The module-boundary invariants, executed as source scans.

A behaviour test cannot see *where* code may do a thing, so the boundary rules — which imports
`core/` may carry, which direction dependencies may point, whether `async` exists anywhere — are
asserted against the sources themselves, the same technique the no-IO case (`I5`) uses.
"""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Final

_SRC: Final = Path(__file__).resolve().parents[2] / "src" / "uniparser2"

_ALLOWED_IMPORTS: Final[dict[str, frozenset[str]]] = {
    # layer -> the `uniparser2.<layer>` roots it may import (stdlib is always allowed); a layer
    # may import itself. `core` is the bottom, `cli` the top and the only facade consumer.
    "core": frozenset({"core"}),
    "ops": frozenset({"core", "ops"}),
    "net": frozenset({"core", "net"}),
    "store": frozenset({"core", "store"}),
    "cli": frozenset({"core", "net", "ops", "store", "cli"}),
}


def _imported_names(tree: ast.Module) -> Iterator[tuple[str, int, str]]:
    """Every absolute import as ``(module, level, name)``; relative imports yield no names."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, 0, "import"
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            yield node.module, 0, "from"


def test_core_imports_the_standard_library_only() -> None:
    """`01` I1: every import under ``core/`` comes from the stdlib or the same package.

    The kernel stays unit-testable and portable — a third-party import at the bottom of the
    dependency graph would make every layer above it pay for an engine the host may not have.
    """
    offenders: list[str] = []
    for path in (_SRC / "core").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for name, _level, kind in _imported_names(tree):
            root = name.split(".")[0]
            if root == "uniparser2" or root not in sys.stdlib_module_names:
                offenders.append(f"core/{path.name}: {kind} {name}")
    assert not offenders, f"`core/` must import the stdlib or itself only, found: {offenders}"


def test_dependencies_point_downward_only() -> None:
    """`01` I2: a layer imports only itself and the layers below it.

    The direction is fixed by `01` §1.1: ``cli → net/store/ops → core``; a cycle is a design
    error, and an upward import would make the kernel depend on the shells around it.
    """
    offenders: list[str] = []
    for layer, allowed in _ALLOWED_IMPORTS.items():
        for path in (_SRC / layer).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for name, _level, kind in _imported_names(tree):
                parts = name.split(".")
                if parts[0] != "uniparser2":
                    continue  # stdlib and third-party imports are I1's and the kernel's business
                target = parts[1] if len(parts) > 1 else ""
                if target == "" and layer == "cli":
                    continue  # `import uniparser2` — the facade, at the top of the graph
                if target not in allowed:
                    offenders.append(f"{layer}/{path.name}: {kind} {name}")
    assert not offenders, f"a layer imported a layer above it, found: {offenders}"


def test_the_kernel_is_fully_synchronous() -> None:
    """`00` N8: there is no ``async`` / ``await`` anywhere in the shipped package.

    Concurrency is the caller's business — it wraps whole runs — so the engine has no awaitable
    path a caller could accidentally block on, and a ``udf`` that answers an awaitable is
    rejected (`UP2-E2009`).
    """
    offenders: list[str] = []
    for path in _SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.AsyncFunctionDef, ast.AsyncFor, ast.AsyncWith, ast.Await)):
                offenders.append(f"{path.relative_to(_SRC)}:{node.lineno} {type(node).__name__}")
    assert not offenders, f"the kernel is fully synchronous, found: {offenders}"
