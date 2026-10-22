"""``re`` operator (design doc 02 §6.3).

**Slots** (see ``02`` §1): ``["re", mode, pattern]`` — the mode is in slot 2 and the pattern in
slot 3. Three modes (replacement and splitting are delegated to ``py``):

| mode | semantics |
|---|---|
| ``search`` | the whole first match (``re.search(...).group(0)``) |
| ``group`` | one capture group of that match (slot 3: ``{"pattern": …, "group": name or index}``) |
| ``findall`` | every match (``re.findall``) |

> The name is ``search`` rather than ``match``: Python's ``re.match`` is **anchored at the start**,
> whereas the semantics here are "find the first one from the start" = ``re.search`` (the ``$match``
> note in the ``04`` draft says exactly "whole match group(0)").

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
_GROUP: Final = "group"
_FINDALL: Final = "findall"

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
    """Regex matching: ``search`` whole match, ``group`` capture group, ``findall`` all matches."""

    summary = "Regex matching (search / group / findall)"
    slot_roles = ("mode", "pattern")
    actions: ClassVar[Mapping[str, ActionSpec]] = {
        _SEARCH: ActionSpec(
            _SEARCH, "the whole first match group(0)", (ParamSpec("pattern", Kind.LITERAL),)
        ),
        _GROUP: ActionSpec(
            _GROUP,
            "take the given capture group",
            (ParamSpec("pattern", Kind.LITERAL), ParamSpec("group", Kind.LITERAL)),
        ),
        _FINDALL: ActionSpec(
            _FINDALL, "findall: every match", (ParamSpec("pattern", Kind.LITERAL),)
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
        if action == _GROUP:
            _check_group(compiled, _literal(params, "group"), pointer=f"{pointer}/group")
        return compiled

    def evaluate(self, call: Call) -> Outcome:
        if not isinstance(call.value, str):
            return Failed(
                code="UP2-E2002",
                reason=f"re.{call.action} needs a str input, got {type_name(call.value)}",
                fix="turn the upstream value into text with py.strip_tags / py.getitem first",
            )
        compiled: re.Pattern[str] = call.payload
        if call.action == _SEARCH:
            found = compiled.search(call.value)
            return Ok(found.group(0)) if found is not None else Ok("")
        if call.action == _FINDALL:
            return Ok(compiled.findall(call.value))
        found_group = compiled.search(call.value)
        if found_group is None:
            return Ok("")
        return Ok(found_group.group(call.params["group"]))


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
                fix="write the pattern as a string",
                pointer=f"/2/{name}",
            )
        )
    return text
