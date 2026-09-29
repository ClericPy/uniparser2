"""The **IO side** of the conformance audit: scan test files and extract "what a case declares it
covers".

There are two declaration styles, both of which must be **visible in the source** (the scanner only
reads source text and never executes tests):

1. Decorator (good for a handful of declarations)::

    @pytest.mark.covers("re", "$match")
    def test_match(...): ...

2. Module-level constant (good for batch declarations, e.g. 24 ``py`` functions)::

    COVERS_PAIRS = (("py", "strip"), ("py", "join"), ...)

Error codes need no marker — a ``UP2-EXXXX`` literal appearing in test source counts as coverage of
that code. The comparison logic is a pure function in ``core.conformance.check`` (01 §1.1 invariant
I1: core never touches the filesystem).
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path

_CODE_PREFIX = "UP2-E"
_CODE_DIGITS = 4
_COVERS_MARK = "covers"
_COVERS_CONSTANT = "COVERS_PAIRS"
DEFAULT_TESTS_ROOT = Path("tests")


def scan_tests(root: Path) -> tuple[set[tuple[str, str]], set[str]]:
    """Scan the test directory and return the covered (operator, action) pairs and error codes."""
    pairs: set[tuple[str, str]] = set()
    codes: set[str] = set()
    for path in sorted(root.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        codes.update(_scan_codes(text))
        pairs.update(_scan_covers(text, path=path))
    return pairs, codes


def _scan_codes(text: str) -> Iterable[str]:
    """Scan for ``UP2-E`` followed by at least 4 digits.

    The digit count must be required: the placeholder form ``UP2-E1xxx`` common in docs and
    comments is not a code, and an early implementation only looked for "digits follow", treated it
    as ``UP2-E1`` and reported a pile of orphan codes.
    """
    start = 0
    while True:
        index = text.find(_CODE_PREFIX, start)
        if index < 0:
            return
        head = index + len(_CODE_PREFIX)
        end = head
        while end < len(text) and text[end].isdigit():
            end += 1
        if end - head >= _CODE_DIGITS:
            yield text[index:end]
        start = max(end, head + 1)


def _scan_covers(text: str, *, path: Path) -> set[tuple[str, str]]:
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:  # pragma: no cover - pytest reports broken test syntax first
        raise SyntaxError(f"{path} cannot be parsed: {exc}") from exc
    found: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for decorator in node.decorator_list:
                pair = _pair_of(decorator)
                if pair is not None:
                    found.add(pair)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            found.update(_pairs_of_constant(node))
    return found


def _pairs_of_constant(node: ast.Assign | ast.AnnAssign) -> set[tuple[str, str]]:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    if not any(
        isinstance(target, ast.Name) and target.id == _COVERS_CONSTANT for target in targets
    ):
        return set()
    value = node.value
    if not isinstance(value, (ast.Tuple, ast.List, ast.Set)):
        return set()
    pairs: set[tuple[str, str]] = set()
    for element in value.elts:
        pair = _literal_pair(element)
        if pair is not None:
            pairs.add(pair)
    return pairs


def _pair_of(node: ast.expr) -> tuple[str, str] | None:
    if not isinstance(node, ast.Call) or not _is_covers(node.func):
        return None
    values = [
        arg.value
        for arg in node.args
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
    ]
    if len(values) < 2:
        return None
    return values[0], values[1]


def _literal_pair(node: ast.expr) -> tuple[str, str] | None:
    if not isinstance(node, (ast.Tuple, ast.List)) or len(node.elts) != 2:
        return None
    values = [
        element.value
        for element in node.elts
        if isinstance(element, ast.Constant) and isinstance(element.value, str)
    ]
    if len(values) != 2:
        return None
    return values[0], values[1]


def _is_covers(node: ast.expr) -> bool:
    if isinstance(node, ast.Attribute):
        return node.attr == _COVERS_MARK
    return isinstance(node, ast.Name) and node.id == _COVERS_MARK
