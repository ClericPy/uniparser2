"""``re`` operator (design doc 02 §6.3).

**Slots** (see ``02`` §1): ``["re", mode, pattern]`` — the mode is in slot 2 and the pattern in
slot 3. Three modes:

| mode | semantics |
|---|---|
| ``search`` | the first match (``group(0)``), or one group with ``[pattern, group]`` |
| ``findall`` | every match (``re.findall``; Python's tuples are encoded as arrays) |
| ``sub`` | replace every match (``[pattern, replacement]``, Python's ``\\N`` / ``\\g<name>``) |

> The name is ``search`` rather than ``match``: Python's ``re.match`` is **anchored at the start**,
> whereas the semantics here are "find the first one from the start" = ``re.search``.

**Current state of ReDoS protection (important)**: Python 3.14's ``re`` has **no** ``timeout``
parameter (measured: the ``re.search`` signature is ``(pattern, string, flags=0)``), so there is no
timeout fallback at runtime. This operator only performs a compile-time static check for **nested
quantifiers** (``UP2-E1013``), and deliberately catches only the most classic shape so that
legitimate patterns such as ``(\\d+\\.)+`` are not falsely rejected. Other ReDoS shapes such as
overlapping alternation cannot be detected statically and completely; that is a known gap (see the
notes in ``core.limits``).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, ClassVar, Final

from ..core.ast import Lit, Param
from ..core.errors import Failed, Ok, Outcome, Up2Error, diag
from ..core.registry import ActionSpec, Call, Kind, Op, ParamSpec, op
from ..core.values import type_name

_SEARCH: Final = "search"
_FINDALL: Final = "findall"
_SUB: Final = "sub"

# Matches only "the whole group is one quantified atom and the whole group is itself quantified":
# `(a+)+` / `(\w*)*` / `(?:[a-z]+)+`. `(\d+\.)+` has several atoms inside, so it does not match
# and is therefore not falsely rejected.
_NESTED_QUANTIFIER: Final = re.compile(r"\(([^()|]*[+*])\)\s*([+*])")
_SINGLE_QUANTIFIED_ATOM: Final = re.compile(r"^(?:\?:)?(?:\\.|\[[^\]]*\]|[^\\()[\]{}|+*?])[+*]$")


def reject_nested_quantifier(pattern: str, /, *, pointer: str = "") -> None:
    """Detect the most classic nested-quantifier shape; a hit raises ``UP2-E1013``."""
    for match in _NESTED_QUANTIFIER.finditer(pattern):
        if _SINGLE_QUANTIFIED_ATOM.match(match.group(1)):
            raise Up2Error(
                diag(
                    "UP2-E1013",
                    (
                        f"pattern {pattern!r} contains a nested quantifier "
                        f"{match.group(0)!r} (ReDoS risk)"
                    ),
                    fix=(
                        "give the inner quantifier an upper bound such as {1,10}, or truncate "
                        "the input before matching"
                    ),
                    pointer=pointer,
                )
            )


@op("re")
class Regex(Op):
    """Regex matching: ``search`` (one group), ``findall``, ``sub``."""

    summary = "Regex matching (search / findall / sub)"
    slot_roles = ("mode", "pattern")
    actions: ClassVar[Mapping[str, ActionSpec]] = {
        _SEARCH: ActionSpec(
            _SEARCH,
            "the first match, or one of its capture groups",
            (
                ParamSpec("pattern", Kind.LITERAL),
                ParamSpec("group", Kind.LITERAL, required=False, default=None),
            ),
        ),
        _FINDALL: ActionSpec(
            _FINDALL, "findall: every match", (ParamSpec("pattern", Kind.LITERAL),)
        ),
        _SUB: ActionSpec(
            _SUB,
            "replace every match (Python's \\N / \\g<name> in the replacement)",
            (ParamSpec("pattern", Kind.LITERAL), ParamSpec("replacement", Kind.LITERAL)),
        ),
    }

    def precompile(
        self, action: str, params: Mapping[str, Param], *, pointer: str = ""
    ) -> re.Pattern[str]:
        pattern = _literal_text(params, "pattern")
        reject_nested_quantifier(pattern, pointer=f"{pointer}/pattern")
        try:
            compiled = re.compile(pattern)
        except re.error as exc:
            raise Up2Error(
                diag(
                    "UP2-E1005",
                    f"regex syntax error: {exc}",
                    fix="fix the pattern",
                    pointer=f"{pointer}/pattern",
                )
            ) from exc
        if action == _SEARCH:
            group = _literal(params, "group")
            if group is not None:
                _check_group(compiled, group, pointer=f"{pointer}/group")
        elif action == _SUB:
            _check_replacement(
                compiled, _literal_text(params, "replacement"), pointer=f"{pointer}/replacement"
            )
        return compiled

    def evaluate(self, call: Call) -> Outcome:
        if not isinstance(call.value, str):
            return Failed(
                code="UP2-E2002",
                reason=f"re.{call.action} needs a str input, got {type_name(call.value)}",
                fix="turn the upstream value into text with py.str / py.getitem first",
            )
        compiled: re.Pattern[str] = call.payload
        if call.action == _SEARCH:
            return _search(compiled, call.value, call.params.get("group"))
        if call.action == _FINDALL:
            return _findall(compiled, call.value)
        return Ok(compiled.sub(str(call.params["replacement"]), call.value))


def _search(compiled: re.Pattern[str], text: str, group: Any) -> Outcome:
    found = compiled.search(text)
    if found is None:
        return Ok("")
    if isinstance(group, str) and group.lstrip("-").isdigit():
        # `_check_group` accepts a numeric string as an index; Python's `group()` would read it
        # as a *name*. Normalize so the spelling the compiler validated is the one that runs.
        group = int(group)
    return Ok(found.group(0 if group is None else group))


def _findall(compiled: re.Pattern[str], text: str) -> Outcome:
    """Python's ``findall`` with tuples encoded as arrays (the value domain has no tuple)."""
    if compiled.groups >= 2:
        return Ok([list(match) for match in compiled.findall(text)])
    return Ok(compiled.findall(text))


def _check_group(compiled: re.Pattern[str], group: Any, *, pointer: str) -> None:
    if isinstance(group, bool):
        raise Up2Error(
            diag(
                "UP2-E1005",
                "group cannot be a boolean",
                fix="write a capture-group index or name",
                pointer=pointer,
            )
        )
    if isinstance(group, int) or (isinstance(group, str) and group.lstrip("-").isdigit()):
        index = int(group)
        if not 0 <= index <= compiled.groups:
            raise Up2Error(
                diag(
                    "UP2-E1005",
                    (
                        f"the pattern has only {compiled.groups} capture groups, "
                        f"so group {index} is unavailable"
                    ),
                    fix="change the group index, or add a capture group to the pattern",
                    pointer=pointer,
                )
            )
        return
    if not isinstance(group, str) or group not in compiled.groupindex:
        named = ", ".join(sorted(compiled.groupindex)) or "(no named groups)"
        raise Up2Error(
            diag(
                "UP2-E1005",
                f"the pattern has no capture group named {group!r} (available: {named})",
                fix="use a named group (?P<name>…) or write the index in group",
                pointer=pointer,
                allowed=tuple(sorted(compiled.groupindex)),
            )
        )


def _check_replacement(compiled: re.Pattern[str], replacement: str, *, pointer: str) -> None:
    """Every ``\\N`` / ``\\g<name>`` is checked against the pattern at compile time."""
    try:
        compiled.sub(replacement, "")
    except (re.error, IndexError) as exc:
        raise Up2Error(
            diag(
                "UP2-E1005",
                f"the replacement is unusable: {exc}",
                fix="fix the group references, or escape a literal backslash as \\\\",
                pointer=pointer,
            )
        ) from exc


def _literal(params: Mapping[str, Param], name: str) -> Any:
    value = params[name]
    return value.value if isinstance(value, Lit) else value


def _literal_text(params: Mapping[str, Param], name: str) -> str:
    text = _literal(params, name)
    if not isinstance(text, str):
        raise Up2Error(
            diag(
                "UP2-E1005",
                f"parameter {name!r} must be a string, got {type_name(text)}",
                fix="write it as a string",
                pointer=f"/2/{name}",
            )
        )
    return text
