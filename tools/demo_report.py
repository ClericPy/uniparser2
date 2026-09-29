"""Build the parsing-chain report grouped by operator and sorted by commonness (real run).

    uv run python tools/demo_report.py         # writes .cache/report/up2-report.html (local)
    uv run python tools/demo_report.py --md    # writes docs/report/up2-report.md (committed)

This is a local development tool, not part of the package: it lives outside `src/` and is not
shipped in the wheel or the sdist. Run it from the repository root, because the output path is
relative to the working directory.

The Markdown catalogue is **committed**, and `tests/report/test_catalogue.py` compares it with a
fresh render (set `UP2_UPDATE_REPORT=1` to rewrite it from a test run) — that is where its freshness
is enforced, not in the workflow. The HTML build carries a timestamp and shows the installed/missing
state of every optional engine, so it stays local.

Structure: the operator is the top-level group (ordered by its own commonness); each
operator gets one section holding its action cards **sorted by commonness** (input → chain →
output repr), the multi-stage compositions starting with that operator and that operator's
compile-time bad chains; mechanisms shared across operators live in the appendix.

Coverage is decided by the **registry enumeration**: every `(operator, action)` pair of
`registry.declared_pairs()` must have a case; a missing one is flagged in red at the top
(nothing is skipped silently).

**Commonness is a design judgement, not telemetry**: tiers follow the "standard action chain
for field extraction": Core (almost always used) / Common / Advanced / Rare. The tier table
lives in this file; changing one line changes the ordering.
"""

from __future__ import annotations

import argparse
import contextlib
import html
import json
import platform
import re
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import uniparser2 as up2
from uniparser2.core import registry

OUT_PATH: Final = Path(".cache/report/up2-report.html")
MD_PATH: Final = Path("docs/report/up2-report.md")
"""The Markdown catalogue is committed (GitHub renders Markdown, not HTML); the HTML is local."""

_LIMIT: Final = 180
_DYNAMIC: Final = registry.DYNAMIC_ACTION_MARK
_BACKTICK_RUN: Final = re.compile(r"`+")

# Commonness tiers: ★★★ Core / ★★ Common / ★ Advanced / ○ Rare. Dict order = sort priority.
TIERS: Final[dict[str, str]] = {
    "Core": "★★★",
    "Common": "★★",
    "Advanced": "★",
    "Rare": "○",
}
_TIER_ORDER: Final = {name: index for index, name in enumerate(TIERS)}

# Commonness order of the operators themselves (first section = most common).
OPERATOR_ORDER: Final = (
    "css",
    "css1",
    "py",
    "xpath",
    "json",
    "re",
    "ctx",
    "const",
    "code",
    "udf",
)

_BADGES: Final[dict[str, str]] = {
    "Ok": "ok",
    "Missing": "miss",
    "Failed": "fail",
    "compile error": "err",
}

HTML_DOC: Final = """
<html>
  <head>
    <meta name="PubDate" content="2026-09-24 15:30:00">
    <title>Notice on Issuing the Government Service Item List</title>
  </head>
  <body>
    <h1 class="article-title">  Notice on Issuing the Government Service Item List  </h1>
    <div class="content">
      <script>console.log('this script must not reach the body');</script>
      <p>To all municipal governments:</p>
      <p>The Government Service Item List is hereby issued to you; please comply.</p>
      <a class="download" href="/files/list.pdf">Download the list</a>
    </div>
    <ul class="rel">
      <li><a href="/p/1.html">Related one</a></li>
      <li><a href="/p/2.html">Related two</a></li>
    </ul>
  </body>
</html>
"""

JSON_DOC: Final = '{"data": {"html": "<p>Body</p>", "list": [{"url": "u1"}, {"url": "u2"}]}}'

XML_DOC: Final = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://x/1</loc><lastmod>2026-09-23</lastmod></url>
  <url><loc>https://x/2</loc><lastmod>2026-09-24</lastmod></url>
</urlset>"""

RSS_DOC: Final = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel><item><title>Headline</title><dc:creator>Jane Reporter</dc:creator></item></channel>
</rss>"""


@dataclass
class Case:
    """One case: an `(operator, action)` pair (or a multi-stage chain) + input + commonness tier."""

    op: str
    action: str
    chain: list[Any]
    value: Any
    tier: str = "Core"
    rank: int = 0
    scope_globals: dict[str, Any] = field(default_factory=dict)
    scope_locals: dict[str, Any] = field(default_factory=dict)
    policy: up2.Policy = up2.DEFAULT_POLICY
    note: str = ""


def _register_demo_udf() -> None:
    up2.register_udf("demo_upper", lambda value: str(value).upper())


@contextlib.contextmanager
def _tight_feed_limit() -> Iterator[None]:
    """Shrink the sandbox time budget (so the appendix over-limit case fires fast), then restore.

    ``0.3`` s, not something razor-thin: a legit sandbox case in the same block (``1 / 0``) must not
    hit the budget by accident — at 50 ms a single scheduling hiccup flipped its outcome from
    ``E2017`` to ``E2016``, which made the committed report differ between runs and the staleness
    check flake. The infinite-loop case still trips the budget immediately (measured warm round
    trips are ~1.3 ms).
    """
    try:
        from uniparser2.ops import code as code_op
    except ImportError:  # pragma: no cover - ops is always installed
        yield
        return
    code_op.configure(max_feed_seconds=0.3)
    try:
        yield
    finally:
        code_op.reset_policy()


def _selector_op(op: str) -> list[Case]:
    """`css` / `css1`: the same set of extraction actions, differing only in cardinality.

    ``key`` is the coverage name (matching the registry) and ``token`` is the action
    **actually written in the chain**; the two differ for the attribute action (the chain
    must name the concrete ``@href``).
    """

    def case(key: str, token: str, selector: str, tier: str, rank: int, note: str = "") -> Case:
        return Case(op, key, [[op, token, selector]], HTML_DOC, tier, rank, note=note)

    return [
        case(
            "text", "text", "h1.article-title", "Core", 1, "plain text (no script/style/noscript)"
        ),
        case("@<attribute>", "@href", "a.download", "Core", 2, "attribute value; absent ⇒ Missing"),
        case("html", "html", "div.content", "Common", 1, "inner HTML"),
        case("remove", "remove", "script,style", "Common", 2, "pure function: pruned copy"),
        case("nodes", "nodes", "ul.rel a", "Common", 3, "node set for L2 fan-out (not a value)"),
        case("outer", "outer", "h1.article-title", "Advanced", 1, "outer HTML (with its own tag)"),
        case("self", "self", "div.content", "Advanced", 2, "handle of the first match"),
    ]


def coverage_cases() -> list[Case]:
    """One case per `(operator, action)` pair (input and parameters picked per operator)."""
    cases: list[Case] = [
        Case(
            "const",
            "const",
            [["const", "article"]],
            HTML_DOC,
            "Core",
            1,
            note="2 positions: literal",
        ),
        Case(
            "code",
            "run",
            [["code", {"src": "ctx.locals.prefix + normalize_space(obj)"}]],
            HTML_DOC,
            "Advanced",
            1,
            scope_locals={"prefix": "Title: "},
            note="sandboxed; optional dependency [code]; the last expression value is returned",
        ),
        Case(
            "json",
            "get",
            [["json", "data.list[*].url"]],
            JSON_DOC,
            "Core",
            1,
            note="2 positions: action slot omitted",
        ),
        Case("xpath", "text", [["xpath", "text", "//*[local-name()='loc']"]], XML_DOC, "Core", 1),
        Case(
            "xpath", "nodes", [["xpath", "nodes", "//*[local-name()='url']"]], XML_DOC, "Common", 1
        ),
        Case(
            "xpath", "self", [["xpath", "self", "//*[local-name()='url']"]], XML_DOC, "Advanced", 1
        ),
        Case(
            "re",
            "search",
            [["re", "search", r"\d{4}-\d{2}-\d{2}"]],
            "published 2026-09-24 end",
            "Core",
            1,
        ),
        Case(
            "re",
            "group",
            [["re", "group", {"pattern": r"(\d{4})-(\d{2})", "group": 2}]],
            "2026-09",
            "Common",
            1,
            note="named object: pattern + group",
        ),
        Case("re", "findall", [["re", "findall", r"\d+"]], "a1b22c333", "Advanced", 1),
        Case(
            "ctx",
            "get",
            [["ctx", "get", "locals.k"]],
            None,
            "Common",
            1,
            scope_locals={"k": "local value"},
        ),
        Case(
            "ctx",
            "set",
            [["ctx", "set", "locals.k"]],
            "written value",
            "Common",
            2,
            note="the write surface is limited to locals/fields",
        ),
        Case(
            "ctx",
            "map",
            [["ctx", "map", {"a": "locals.x", "b": "locals.y"}]],
            None,
            "Advanced",
            1,
            scope_locals={"x": 1, "y": 2},
            note="named-object form → dict",
        ),
        Case(
            "ctx",
            "del",
            [["ctx", "del", "locals.k"]],
            "upstream value",
            "Rare",
            1,
            scope_locals={"k": 1},
        ),
        Case(
            "udf",
            _DYNAMIC,
            [["udf", "demo_upper", ""]],
            "hello",
            "Common",
            1,
            note="dynamic action space: slot 2 carries the host-registered function name",
        ),
    ]
    cases += _selector_op("css") + _selector_op("css1") + _py_cases()
    return cases


def _py_cases() -> list[Case]:
    """`py`  has 31 allowlisted functions, tiered by commonness (module docstring)."""
    spec: list[tuple[str, int, str, Any, Any, str]] = [
        ("Core", 1, "strip", "  text  ", "", "strip leading/trailing whitespace"),
        ("Core", 2, "normalize_space", "a   b\n c", "", "collapse consecutive whitespace"),
        ("Core", 3, "urljoin", "a.html", "https://x/p/", "relative to absolute (pass base)"),
        (
            "Core",
            4,
            "first",
            ["a", "b"],
            "",
            "first item (xpath/css yield a list; a scalar is needed)",
        ),
        ("Core", 5, "get", {"k": 7}, "k", "dict key lookup (missing key ⇒ Missing)"),
        ("Core", 6, "len", [1, 2, 3], "", "length"),
        ("Core", 7, "slice", "abcdef", ":3", 'slice: ":3" / "1:5" / "::-1"'),
        (
            "Core",
            8,
            "default",
            "",
            "fallback value",
            "fallback for empty/None/missing (accepts_missing)",
        ),
        ("Common", 1, "getitem", ["a", "b"], 1, "list index (out of range ⇒ Missing)"),
        ("Common", 2, "last", [1, 2], "", "last item"),
        ("Common", 3, "replace", "old document", ["old", "new"], "replace all (positional array)"),
        ("Common", 4, "split", "a,b,c", ",", "split on a separator"),
        ("Common", 5, "join", ["a", "b"], "-", "join a list"),
        ("Common", 6, "strip_tags", "<b>text</b>", "", "strip HTML tags"),
        (
            "Common",
            7,
            "parse_time",
            "2026-09-24 15:30:00",
            "",
            "time normalization (0 required dependencies)",
        ),
        (
            "Common",
            8,
            "html_to_markdown",
            "<h1>Heading</h1><p>a <b>b</b></p>",
            "",
            "optional dependency [md]",
        ),
        ("Common", 9, "int", "42", "", "type conversion (formerly cast int)"),
        ("Common", 10, "str", 42, "", "type conversion (formerly cast str)"),
        ("Advanced", 1, "upper", "abc", "", "uppercase"),
        ("Advanced", 2, "lower", "ABC", "", "lowercase"),
        ("Advanced", 3, "flatten", [[1, 2], [3]], "", "flatten one level"),
        ("Advanced", 4, "sort", [3, 1, 2], "", "stable sort"),
        ("Advanced", 5, "uniq", [1, 1, 2], "", "deduplicate, keeping order"),
        (
            "Advanced",
            6,
            "urlsplit",
            "https://x/a?q=1",
            "netloc",
            "URL parts (take the site identity)",
        ),
        ("Advanced", 7, "b64_decode", "YWJj", "", "Base64 decode"),
        ("Advanced", 8, "sha256", "abc", "", "hex digest (idempotency key)"),
        ("Advanced", 9, "from_json", '{"a": 1}', "", "JSON text → JSON tree (formerly cast json)"),
        ("Advanced", 10, "float", "1.5", "", "type conversion"),
        ("Advanced", 11, "bool", "no", "", "type conversion (falsey word list)"),
        ("Advanced", 12, "list", '["a","b"]', "", "JSON array text → list"),
        ("Rare", 1, "b64_encode", "abc", "", "Base64 encode"),
    ]
    return [
        Case("py", name, [["py", name, params]], value, tier, rank, note=note)
        for tier, rank, name, value, params, note in spec
    ]


def chain_cases() -> list[Case]:
    """Multi-stage chains (attributed to the operator section they **start with**)."""
    return [
        Case(
            "css1",
            "composition",
            [["css1", "text", "h1.article-title"], ["py", "normalize_space", ""]],
            HTML_DOC,
            note="take the heading → normalize whitespace",
        ),
        Case(
            "css1",
            "composition",
            [["css1", "@href", "a.download"], ["py", "urljoin", "https://x/p/"]],
            HTML_DOC,
            note="take the attribute → build the absolute URL",
        ),
        Case(
            "css",
            "composition",
            [
                ["css", "remove", "script,style"],
                ["css1", "html", "div.content"],
                ["py", "html_to_markdown", ""],
            ],
            HTML_DOC,
            note="prune → take HTML → convert to Markdown (the standard body-extraction trio)",
        ),
        Case(
            "css",
            "composition",
            [["css", "@href", "ul.rel a"]],
            HTML_DOC,
            note="css yields a list: every href at once",
        ),
        Case(
            "css",
            "composition",
            [["css", "nodes", "ul.rel a"], ["py", "len", ""]],
            HTML_DOC,
            note="node set → count",
        ),
        Case(
            "css",
            "composition",
            [["css1", "text", "h1.article-title"], ["code", {"src": "normalize_space(obj)"}]],
            HTML_DOC,
            note="extract → process in the sandbox (allowlisted functions need no import)",
        ),
        Case(
            "py",
            "composition",
            [["py", "from_json", ""], ["json", "data.html"]],
            JSON_DOC,
            note="parse the JSON text first, then use the json operator to take a subtree",
        ),
        Case(
            "py",
            "composition",
            [["py", "urljoin", "$globals.base"]],
            "a.html",
            scope_globals={"base": "https://example.gov.cn/p/"},
            note="a parameter referencing globals",
        ),
        Case(
            "py",
            "composition",
            [["py", "str", ""], ["re", "search", r"\d+"], ["py", "int", ""]],
            2026,
            note="convert → regex → convert again",
        ),
        Case(
            "py",
            "composition",
            [["py", "parse_time", ""], ["py", "slice", ":10"]],
            "2026/09/24 15:30:00",
            note="time normalization → take the date part",
        ),
        Case(
            "json",
            "composition",
            [["json", "data.list[*].url"], ["py", "first", ""]],
            JSON_DOC,
            note="take all URLs → take the first",
        ),
        Case(
            "re",
            "composition",
            [["re", "search", r"\d{4}-\d{2}-\d{2}"], ["re", "search", r"\d{4}"]],
            "published 2026-09-24 end",
            note="whole text → the year inside it",
        ),
        Case(
            "xpath",
            "composition",
            [["xpath", "text", "//*[local-name()='lastmod']"], ["py", "last", ""]],
            XML_DOC,
            note="sitemap: every lastmod → take the last",
        ),
        Case(
            "xpath",
            "composition",
            [
                [
                    "xpath",
                    "text",
                    {"expr": "//dc:creator", "ns": {"dc": "http://purl.org/dc/elements/1.1/"}},
                ]
            ],
            RSS_DOC,
            note="namespace prefix: slot 3 takes an object form carrying the ns map",
        ),
        Case(
            "ctx",
            "composition",
            [["ctx", "set", "locals._tmp"], ["ctx", "get", "locals._tmp"]],
            "intermediate value",
            note="write to locals → read back (the `_` prefix = internal path)",
        ),
    ]


def edge_cases() -> list[Case]:
    """Appendix: tri-state and policy (cross-operator, so not in an operator section)."""
    return [
        Case("tri-state", "Ok (hit)", [["css1", "text", "h1.article-title"]], HTML_DOC),
        Case(
            "tri-state",
            'Missing → default policy empty ⇒ Ok("")',
            [["css1", "text", "div.nope"]],
            HTML_DOC,
            note="default on_missing=empty",
        ),
        Case(
            "tri-state",
            "Missing (kept as is)",
            [["css1", "text", "div.nope"]],
            HTML_DOC,
            policy=up2.Policy(on_missing="drop"),
            note="on_missing=drop",
        ),
        Case(
            "tri-state",
            "Failed (input type mismatch)",
            [["py", "strip_tags", ""]],
            42,
            note="UP2-E2002",
        ),
        Case(
            "tri-state", "Failed (evaluation failed)", [["py", "int", ""]], "abc", note="UP2-E2005"
        ),
        Case(
            "tri-state",
            "Failed (Missing required to raise)",
            [["css1", "text", "div.nope"]],
            HTML_DOC,
            policy=up2.Policy(on_missing="raise"),
            note="on_missing=raise ⇒ UP2-E2015",
        ),
        Case(
            "policy",
            "on_missing=empty",
            [["css1", "text", "div.nope"]],
            HTML_DOC,
            policy=up2.Policy(on_missing="empty"),
        ),
        Case(
            "policy",
            "on_missing=none",
            [["css1", "text", "div.nope"]],
            HTML_DOC,
            policy=up2.Policy(on_missing="none"),
        ),
        Case(
            "policy",
            "on_error=drop (treat a failure as missing)",
            [["py", "int", ""]],
            "abc",
            policy=up2.Policy(on_error="drop"),
        ),
        Case(
            "policy",
            "on_error=empty (a failure falls back to an empty string)",
            [["py", "int", ""]],
            "abc",
            policy=up2.Policy(on_error="empty"),
        ),
        Case(
            "tri-state",
            "Failed (sandbox code raised)",
            [["code", {"src": "1 / 0"}]],
            None,
            note="UP2-E2017 (the sandbox code can catch it with try/except)",
        ),
        Case(
            "tri-state",
            "Failed (sandbox execution over limit)",
            [["code", {"src": "while True:\n    pass"}]],
            None,
            note="UP2-E2016: limits are configured by the host (a tiny time budget is used here)",
        ),
    ]


def form_cases() -> list[Case]:
    """Appendix: the four parameter-slot forms, plus reference / directive objects."""
    return [
        Case("form", "scalar parameter", [["py", "urljoin", "https://x/p/"]], "a.html"),
        Case("form", "positional array", [["py", "replace", ["old", "new"]]], "old text"),
        Case("form", "named object", [["re", "group", {"pattern": r"(\d+)", "group": 1}]], "x42"),
        Case(
            "form",
            "reference ($globals / $locals)",
            [["py", "urljoin", "$globals.base"]],
            "a",
            scope_globals={"base": "https://x/"},
        ),
        Case(
            "form",
            'directive object {"$lit": …}: a literal starting with $',
            [["py", "default", {"$lit": "$fields.title"}]],
            "",
            note="without $lit it is a reference (E1006, see the invalid-form sections)",
        ),
        Case(
            "form",
            "css empty selector = the current node itself",
            [["css1", "text", ""]],
            "<p>plain text supplied directly</p>",
        ),
    ]


def bad_chains() -> list[list[Any]]:
    """Compile-time bad chains (attributed to the operator of the first stage)."""
    return [
        [["py", "strip"]],
        [["py", "strip", "", ""]],
        [["py", "no_such_function", ""]],
        [["py", "parse_time", {"format": "%Q"}]],
        [["py", "default", "$nope.x"]],
        # A container where the function's own runtime path needs a scalar: the named-object form of
        # a single-parameter function, an array, and an unknown enum value.
        [["py", "urljoin", {"base": "https://example.com/news/"}]],
        [["py", "slice", {"spec": "0:4"}]],
        [["py", "getitem", {"index": {}}]],
        [["py", "split", {"sep": ",", "maxsplit": {}}]],
        [["py", "sort", {"key": {}}]],
        [["css", "txt", "h1"]],
        [["css", "@", "h1"]],
        [["css", "text", "!!!"]],
        [["css", "$text", "h1"]],
        [["re", "group", {"pattern": "a", "group": 9}]],
        [["xpath", "text", "//dc:creator"]],
        [["json", "("]],
        [["udf", "not_registered", ""]],
        [["ctx", "set", "globals.x"]],
        [["nope", "strip", ""]],
    ]


@dataclass
class Ran:
    case: Case
    state: str
    outcome_repr: str
    steps: list[tuple[str, str]]
    error: up2.Diagnostic | None = None

    @property
    def owner(self) -> str:
        """Owning operator: a multi-stage chain belongs to its first stage, a bad chain to the
        operator its first stage declares."""
        first = self.case.chain[0]
        return str(first[0]) if isinstance(first, list) and first else self.case.op


_LIMIT_MEASURE: Final = re.compile(r"feed time limit exceeded: \S+ > \S+")


def _stable_text(text: str) -> str:
    """Collapse the measured sandbox duration in a limit message.

    The duration differs on every run, and it is 7-10 characters wide, so it also moves the tail of
    the 180-character truncation window (`algo…` vs `algori…`). With it collapsed before truncation,
    both renderers produce the same bytes on every run — the committed catalogue and its staleness
    check depend on that.
    """
    return _LIMIT_MEASURE.sub("feed time limit exceeded: <measured>", text)


def _render_value(value: Any) -> str:
    text = _stable_text(repr(value))
    return text if len(text) <= _LIMIT else text[:_LIMIT] + "…"


def _run(case: Case) -> Ran:
    steps: list[tuple[str, str]] = []
    for index in range(1, len(case.chain) + 1):
        scope = up2.Scope(globals=dict(case.scope_globals), locals=dict(case.scope_locals))
        try:
            prefix = up2.compile_field(case.chain[:index])
        except up2.Up2Error as exc:
            return Ran(case, "compile error", "", steps, exc.diagnostic)
        outcome = up2.eval_field(prefix, case.value, scope=scope, policy=case.policy)
        steps.append(
            (json.dumps(case.chain[index - 1], ensure_ascii=False), _render_value(outcome))
        )
    scope = up2.Scope(globals=dict(case.scope_globals), locals=dict(case.scope_locals))
    try:
        compiled = up2.compile_field(case.chain)
    except up2.Up2Error as exc:
        return Ran(case, "compile error", "", [], exc.diagnostic)
    outcome = up2.eval_field(compiled, case.value, scope=scope, policy=case.policy)
    return Ran(case, type(outcome).__name__, _render_value(outcome), steps)


def _escape(text: object) -> str:
    return html.escape(str(text), quote=False)


def _io(label: str, body: str) -> str:
    return f'<div class="io"><span class="label">{label}</span>{body}</div>'


def _pre(text: str, *, css: str = "") -> str:
    klass = f' class="{css}"' if css else ""
    return f"<pre{klass}>{text}</pre>"


def _error_text(diagnostic: up2.Diagnostic) -> str:
    return (
        f"{diagnostic.code} pointer={diagnostic.pointer}  {diagnostic.message}\n"
        f"fix: {diagnostic.fix}\nallowed: {list(diagnostic.allowed)}"
    )


def _action_index() -> dict[tuple[str, str], registry.ActionReport]:
    return {
        (item.name, action.name): action for item in registry.report() for action in item.actions
    }


_FORM_TEXT: Final[dict[str, str]] = {
    "none": 'no parameter (write two positions, or "")',
    "value": "the value itself",
    "named": "a named object (a positional array also works)",
}
"""How the parameter slot is written, per ``registry.ParamForm`` (design note 02 §4)."""


def _schema_text(action: registry.ActionReport | None) -> str:
    if action is None:
        return "dynamic action space (the function name is host-registered)"
    form = _FORM_TEXT.get(str(action.param_form), str(action.param_form))
    prefix = f"parameter slot: {form}"
    if not action.params:
        return prefix
    parts = []
    for param in action.params:
        flag = "required" if param.required else f"optional, default {param.default!r}"
        parts.append(f"{param.name}: {param.kind} ({flag})")
    return f"{prefix} · " + " · ".join(parts)


def _tier_badge(tier: str) -> str:
    mark = TIERS.get(tier, "")
    return f'<span class="tier" title="{_escape(tier)}">{_escape(mark)}</span>'


def _chain_html(ran: Ran) -> str:
    if len(ran.steps) > 1:
        body = "".join(
            f'<div class="step"><code>{_escape(step)}</code>'
            f'<span class="arrow">→</span><code class="out">{_escape(out)}</code></div>'
            for step, out in ran.steps
        )
        return _io("Chain (step by step)", f'<div class="steps">{body}</div>')
    chain = json.dumps(ran.case.chain, ensure_ascii=False)
    return _io("Chain", _pre(_escape(chain)))


def _case_card(
    ran: Ran,
    action: registry.ActionReport | None,
    *,
    shared_input: str,
    anchor: str,
) -> str:
    """One card.

        ``action`` being ``None`` means this is not "one action of some operator" (multi-stage
    compositions, and the tri-state / form cases in the appendix); then the commonness tier
        and the parameter schema are not shown, because those two are properties of an **action**.
    """
    kind = _BADGES.get(ran.state, "miss")
    note = f'<span class="note">{_escape(ran.case.note)}</span>' if ran.case.note else ""
    deps = ""
    if action is not None and action.requires and not action.available:
        missing = ", ".join(action.missing) or ", ".join(action.requires)
        deps = f'<span class="warn">missing {_escape(missing)}</span>'
    title = f'<span class="pair">{_escape(ran.case.action)}</span>'
    if action is not None:
        title = (
            f"{_tier_badge(ran.case.tier)}{title}"
            f'<code class="summary">{_escape(action.summary)}</code>'
        )
    head = (
        f'<div class="card"><div class="head">'
        f'<span class="badge {kind}">{_escape(ran.state)}</span>'
        f"{title}{note}{deps}</div>"
    )
    rows = [head]
    if action is not None:
        rows.append(_io("Parameters", _pre(_escape(_schema_text(action)))))
    own = _render_value(ran.case.value)
    if own != shared_input or not shared_input:
        rows.append(_io("Input", _pre(_escape(own))))
    else:
        rows.append(
            _io("Input", f'<span class="ref">same as <a href="#{anchor}">sample above</a></span>')
        )
    rows.append(_chain_html(ran))
    rows.append(_io("Output", _pre(_escape(ran.outcome_repr), css="result")))
    if ran.error is not None:
        rows.append(_io("Diagnostics", _pre(_escape(_error_text(ran.error)))))
    rows.append("</div>")
    return "".join(rows)


def _bad_table(rows: list[tuple[list[Any], str, str, str, str]]) -> str:
    head = (
        "<table><tr><th>Bad chain</th><th>Error code</th><th>pointer</th><th>Message</th>"
        "<th>Fix</th></tr>"
    )
    body = "".join(
        f"<tr><td><code>{_escape(json.dumps(chain, ensure_ascii=False))}</code></td>"
        f"<td><code>{_escape(code)}</code></td>"
        f"<td><code>{_escape(pointer)}</code></td>"
        f"<td>{_escape(message)}</td><td>{_escape(fix)}</td></tr>"
        for chain, code, pointer, message, fix in rows
    )
    return head + body + "</table>"


def _operator_section(
    item: registry.OpReport,
    cases: list[Ran],
    chains: list[Ran],
    bad: list[tuple[list[Any], str, str, str, str]],
) -> str:
    anchor = f"input-{item.name}"
    values = {_render_value(ran.case.value) for ran in cases}
    shared_input = values.pop() if len(values) == 1 else ""
    counts: dict[str, int] = {}
    for ran in cases:
        counts[ran.case.tier] = counts.get(ran.case.tier, 0) + 1
    tier_text = " / ".join(f"{TIERS[t]} {t} {counts[t]}" for t in TIERS if t in counts)
    alias = f" · aliases {'/'.join(item.aliases)}" if item.aliases else ""
    deps = ", ".join(item.requires) if item.requires else "none"
    state = "installed" if item.available else f"missing ({', '.join(item.missing)})"
    sample = ""
    if shared_input:
        sample = (
            f'<details class="doc" id="{anchor}">'
            "<summary>Input sample for this section (shared by all entries)</summary>"
            f"{_pre(_escape(shared_input))}</details>"
        )
    ordered = sorted(cases, key=lambda ran: (_TIER_ORDER.get(ran.case.tier, 9), ran.case.rank))
    index = _action_index()
    cards = "".join(
        _case_card(
            ran,
            index.get((item.name, ran.case.action)),
            shared_input=shared_input,
            anchor=anchor,
        )
        for ran in ordered
    )
    chain_cards = "".join(
        _case_card(r, index.get((item.name, r.case.action)), shared_input="", anchor=anchor)
        for r in chains
    )
    chain_block = f"<h3>Compositions (multi-stage chains)</h3>{chain_cards}" if chains else ""
    bad_block = f"<h3>Invalid forms</h3>{_bad_table(bad)}" if bad else ""
    return (
        f'<section class="op" id="op-{item.name}">'
        f"<h2><code>{_escape(item.name)}</code> {_escape(item.summary)}</h2>"
        f'<p class="meta">Arity {item.arity} · Slots '
        f"{' / '.join(f'slot {i + 2}={role}' for i, role in enumerate(item.slots))}"
        f" · Dependencies {_escape(deps)} ({_escape(state)}){_escape(alias)}"
        f" · {len(item.actions)} actions ({_escape(tier_text)})</p>"
        f"{sample}"
        f"<h3>Actions (sorted by commonness)</h3>{cards}"
        f"{chain_block}{bad_block}</section>"
    )


def _coverage_block(all_runs: list[Ran], unexpected: list[Ran]) -> str:
    declared = registry.declared_pairs()
    covered = {(case.op, case.action) for case in coverage_cases()}
    missing = sorted(pair for pair in declared if pair not in covered)
    extra = sorted(pair for pair in covered if pair not in declared)
    states: dict[str, int] = {}
    for ran in all_runs:
        states[ran.state] = states.get(ran.state, 0) + 1
    state_text = ", ".join(f"{name} {count}" for name, count in sorted(states.items()))
    if missing or extra:
        banner = f'<div class="banner bad">Coverage gap: missing {missing}, extra {extra}</div>'
    elif unexpected:
        names = ", ".join(f"{ran.case.op}.{ran.case.action}" for ran in unexpected)
        banner = (
            '<div class="banner bad">'
            f"{len(unexpected)} of the full behavior cases are not Ok (a fixture may be wrong): "
            f"{_escape(names)}</div>"
        )
    else:
        banner = (
            f'<div class="banner good">Coverage check passed: the registry declares '
            f"{len(declared)} pairs = {len(covered)} pairs covered by cases (0 missing) · "
            "every behavior case produced Ok</div>"
        )
    rows = "".join(
        f'<tr><td><a href="#op-{item.name}"><code>{_escape(item.name)}</code></a></td>'
        f"<td>{item.arity}</td>"
        f"<td>{_escape(' / '.join(item.slots))}</td>"
        f"<td>{_escape(item.summary)}</td><td>{len(item.actions)}</td></tr>"
        for item in sorted(
            registry.report(),
            key=lambda i: OPERATOR_ORDER.index(i.name) if i.name in OPERATOR_ORDER else 99,
        )
    )
    # Anti-drift: an operator registered but absent from this order must stand out, so it
    # cannot quietly fall to the end and break the header counts.
    unlisted = sorted(item.name for item in registry.report() if item.name not in OPERATOR_ORDER)
    if unlisted:
        banner += (
            '<div class="banner bad">Missing from the operator order table: '
            f"{_escape(', '.join(unlisted))} (add them to OPERATOR_ORDER)</div>"
        )
    return (
        banner
        + f'<p class="meta">{len(tuple(registry.report()))} operators · '
        + f"{len(declared)} declared pairs · case state distribution: {_escape(state_text)}</p>"
        + "<table><tr><th>Operator (sorted by commonness)</th><th>Arity</th>"
        + "<th>Slots</th><th>Summary</th>"
        + f"<th>Actions</th></tr>{rows}</table>"
    )


def _tier_legend() -> str:
    rows = "".join(
        f"<tr><td>{_escape(TIERS[name])}</td><td>{_escape(name)}</td><td>{_escape(desc)}</td></tr>"
        for name, desc in _TIER_DESC.items()
    )
    return (
        '<p class="sub">Commonness is a **design judgement** (tiers follow the "standard action '
        'chain for field extraction"), not telemetry; the order lives in the tier table of '
        "<code>tools/demo_report.py</code>.</p>"
        f"<table><tr><th>Tier</th><th>Name</th><th>Meaning</th></tr>{rows}</table>"
    )


_TIER_DESC: Final[dict[str, str]] = {
    "Core": "almost always used for field extraction",
    "Common": "a regular for cleaning / extraction / URL building",
    "Advanced": "list handling, encodings, specific formats",
    "Rare": "fallbacks or rarely used",
}


_BadRow = tuple[list[Any], str, str, str, str]
# One invalid form: (chain, error code, pointer, message, fix).


@dataclass(frozen=True, slots=True)
class _RunSet:
    """Every case, already run for real. The HTML and the Markdown renderer read the same runs."""

    coverage: list[Ran]
    chains: list[Ran]
    edges: list[Ran]
    forms: list[Ran]
    bad_rows: list[_BadRow]

    @property
    def all_runs(self) -> list[Ran]:
        return self.coverage + self.chains + self.edges + self.forms

    def sections(self) -> list[tuple[registry.OpReport, list[Ran], list[Ran], list[_BadRow]]]:
        """``(operator, its action cases, its composition cases, its invalid forms)`` in order."""
        out: list[tuple[registry.OpReport, list[Ran], list[Ran], list[_BadRow]]] = []
        for item in sorted(
            registry.report(),
            key=lambda i: OPERATOR_ORDER.index(i.name) if i.name in OPERATOR_ORDER else 99,
        ):
            cases = [ran for ran in self.coverage if ran.case.op == item.name]
            if not cases:
                continue
            chains = [ran for ran in self.chains if ran.owner == item.name]
            bad = [row for row in self.bad_rows if row[0][0][0] == item.name]
            out.append((item, cases, chains, bad))
        return out

    def orphan_bad(self) -> list[_BadRow]:
        """Invalid forms whose first operator is not one of the ten (attributed to nobody)."""
        return [row for row in self.bad_rows if row[0][0][0] not in OPERATOR_ORDER]


def _collect() -> _RunSet:
    """Run every case once; a fixture that is not ``Ok`` is reported by ``behavior_failures``."""
    _register_demo_udf()
    coverage = [_run(case) for case in coverage_cases()]
    chains = [_run(case) for case in chain_cases()]
    # The "over limit" appendix case needs a real (tiny) time budget: limits are not in the chain.
    with _tight_feed_limit():
        edges = [_run(case) for case in edge_cases()]
    forms = [_run(case) for case in form_cases()]

    bad_rows: list[_BadRow] = []
    for chain in bad_chains():
        try:
            up2.compile_field(chain)
            bad_rows.append((chain, "unexpected: no error raised", "", "", ""))
        except up2.Up2Error as exc:
            diagnostic = exc.diagnostic
            bad_rows.append(
                (
                    chain,
                    diagnostic.code,
                    diagnostic.pointer,
                    diagnostic.message,
                    diagnostic.fix,
                )
            )
    return _RunSet(coverage, chains, edges, forms, bad_rows)


def build_html() -> str:
    runs = _collect()
    all_runs = runs.all_runs
    sections = [
        _operator_section(item, cases, chains, bad) for item, cases, chains, bad in runs.sections()
    ]
    orphan_bad = runs.orphan_bad()
    stamp = datetime.now(UTC).astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
    meta = (
        "Input → triple chain → output repr (all of it produced by a real run of "
        "<code>uv run python tools/demo_report.py</code>)<br>"
        f"Generated {_escape(stamp)} · Python {_escape(platform.python_version())} · "
        f"uniparser2 {_escape(up2.__version__)} · Platform {_escape(platform.system())} "
        f"{_escape(platform.release())}"
    )
    toc = (
        '<p class="toc"><a href="#coverage">Coverage check</a>'
        + "".join(f'<a href="#op-{name}">{name}</a>' for name in OPERATOR_ORDER)
        + '<a href="#appendix">Appendix: shared by all operators</a></p>'
    )
    appendix = (
        '<section id="appendix"><h2>Appendix: mechanisms shared by all operators</h2>'
        '<p class="sub">These sections are **not grouped by operator**: tri-state, policy and '
        "parameter forms are mechanisms shared by every operator, so slicing them per "
        "operator would hide the differences.</p>"
        "<h3>A. Tri-state and policy</h3>"
        '<p class="sub">Defaults are on_missing=empty and on_error=raise, so "no match" falls '
        'back to Ok("") by default.</p>'
        + "".join(_case_card(ran, None, shared_input="", anchor="appendix") for ran in runs.edges)
        + "<h3>B. Parameter forms</h3>"
        '<p class="sub">The scalar / positional array / named object / reference / '
        "directive object forms of a parameter slot (slot 3).</p>"
        + "".join(_case_card(ran, None, shared_input="", anchor="appendix") for ran in runs.forms)
        + "<h3>C. Bad chains owned by no operator</h3>"
        + _bad_table(orphan_bad)
        + "</section>"
    )
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en"><head><meta charset="utf-8">\n'
        "<title>uniparser2 parsing-chain report (grouped by operator · real run)</title>"
        f"<style>{_CSS}</style></head><body>\n"
        "<h1>uniparser2 parsing-chain report</h1>\n"
        f'<p class="meta">{meta}</p>\n'
        f"{toc}\n"
        '<section id="coverage"><h2>Coverage check and operator table</h2>'
        f"{_coverage_block(all_runs, behavior_failures())}</section>\n"
        '<section id="tiers"><h2>Commonness tiers</h2>'
        f"{_tier_legend()}</section>\n" + "\n".join(sections) + "\n"
        f"{appendix}\n"
        "</body></html>\n"
    )


def _md_fence(text: str, lang: str = "") -> str:
    """A fence long enough to survive backticks inside ``text``."""
    longest = max((len(run) for run in _BACKTICK_RUN.findall(text)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}{lang}\n{text}\n{fence}"


def _md_inline(value: object) -> str:
    """Inline code; a backtick inside the value is handled the GFM way (wider delimiters)."""
    body = str(value)
    return f"`{body}`" if "`" not in body else f"`` {body} ``"


def _md_cell(value: object, *, code: bool = False) -> str:
    """A table cell: escape pipes and fold newlines; ``code`` wraps it in inline code."""
    body = str(value).replace("|", "\\|").replace("\n", "<br>")
    return _md_inline(body) if code else body


def _md_parameters(action: registry.ActionReport | None) -> str:
    if action is None:
        return "dynamic action space (the function name is host-registered)"
    form = _FORM_TEXT.get(str(action.param_form), str(action.param_form))
    if not action.params:
        return f"parameter slot: {form}"
    declared = ", ".join(
        f"`{param.name}: {param.kind}"
        + ("" if param.required else f"?, default {param.default!r}")
        + "`"
        for param in action.params
    )
    return f"parameter slot: {form} · {declared}"


def _md_case(ran: Ran, action: registry.ActionReport | None, *, shared_input: str) -> str:
    out = [f"#### `{ran.case.action}` — {action.summary if action else ran.case.op}"]
    bits = [f"tier {TIERS.get(ran.case.tier, '')} {ran.case.tier}"]
    if action is not None:
        bits.append(_md_parameters(action))
    out.append("- " + " · ".join(bits))
    if ran.case.note:
        out.append(f"- note: {ran.case.note}")
    if len(ran.steps) > 1:
        out.append("- chain:")
        out.extend(f"  - {_md_inline(step)} → {_md_inline(result)}" for step, result in ran.steps)
    else:
        out.append(f"- chain: {_md_inline(json.dumps(ran.case.chain, ensure_ascii=False))}")
    own = _render_value(ran.case.value)
    if own != shared_input or not shared_input:
        out.append(f"- input: {_md_inline(own)}")
    else:
        out.append("- input: the shared sample above")
    out.append(f"- output: {_md_inline(ran.outcome_repr)} ({ran.state})")
    if ran.error is not None:
        out.append(f"- diagnostics: {_md_inline(ran.error)}")
    return "\n".join(out) + "\n"


def _md_bad_table(rows: list[_BadRow]) -> str:
    head = "| invalid chain | code | pointer | message | fix |\n|---|---|---|---|---|\n"
    body = "".join(
        f"| {_md_cell(json.dumps(row[0], ensure_ascii=False), code=True)} "
        f"| {_md_cell(row[1], code=True)} | {_md_cell(row[2], code=True)} "
        f"| {_md_cell(row[3])} | {_md_cell(row[4])} |\n"
        for row in rows
    )
    return head + body


def _md_section(
    item: registry.OpReport, cases: list[Ran], chains: list[Ran], bad: list[_BadRow]
) -> str:
    index = _action_index()
    deps = ", ".join(f"`{name}`" for name in item.requires) or "none"
    slots = " / ".join(f"slot {i + 2}={role}" for i, role in enumerate(item.slots))
    tiers = sorted({ran.case.tier for ran in cases}, key=lambda name: _TIER_ORDER.get(name, 9))
    out = [
        f"## `{item.name}` — {item.summary}",
        "",
        f"arity {item.arity} · {slots} · dependencies: {deps} · {len(item.actions)} actions "
        f"({', '.join(tiers)})",
        "",
    ]
    shared = _render_value(cases[0].case.value)
    out += ["Shared input for this section:", "", _md_fence(str(shared), "text"), ""]
    out.append("### Actions (sorted by commonness)")
    out.append("")
    ordered = sorted(cases, key=lambda ran: (_TIER_ORDER.get(ran.case.tier, 9), ran.case.rank))
    for ran in ordered:
        out.append(_md_case(ran, index.get((item.name, ran.case.action)), shared_input=shared))
    if chains:
        out += ["### Compositions (multi-stage chains)", ""]
        for ran in chains:
            out.append(_md_case(ran, index.get((item.name, ran.case.action)), shared_input=""))
    if bad:
        out += ["### Invalid forms", "", _md_bad_table(bad)]
    return "\n".join(out) + "\n"


def _md_coverage(runs: _RunSet, unexpected: list[Ran]) -> str:
    declared = registry.declared_pairs()
    covered = {(case.op, case.action) for case in coverage_cases()}
    missing = sorted(pair for pair in declared if pair not in covered)
    states: dict[str, int] = {}
    for ran in runs.all_runs:
        states[ran.state] = states.get(ran.state, 0) + 1
    state_text = ", ".join(f"`{name}` {count}" for name, count in sorted(states.items()))
    verdict = (
        "**Coverage check passed**: every declared pair has a case and every behavior case "
        "ran `Ok`."
        if not missing and not unexpected
        else f"**Coverage gap**: missing {missing} · non-Ok behavior cases "
        f"{[f'{ran.case.op}.{ran.case.action}' for ran in unexpected]}"
    )
    rows = "".join(
        f"| `{item.name}` | {item.arity} | {' / '.join(item.slots)} | {_md_cell(item.summary)} "
        f"| {len(item.actions)} |\n"
        for item, *_ in runs.sections()
    )
    return (
        "## Coverage check\n\n"
        f"- {verdict}\n"
        f"- the registry declares **{len(declared)}** pairs = **{len(covered)}** pairs covered "
        "by cases\n"
        f"- states across every run: {state_text}\n\n"
        "| operator | arity | slots | summary | actions |\n|---|---|---|---|---|\n" + rows + "\n"
    )


def _md_tier_legend() -> str:
    rows = "".join(
        f"| {TIERS[name]} | {name} | {_md_cell(desc)} |\n" for name, desc in _TIER_DESC.items()
    )
    return (
        "## Commonness tiers\n\n"
        'Commonness is a **design judgement**, not telemetry: the tiers follow the "standard '
        'action chain for field extraction", and the table lives in `tools/demo_report.py`.\n\n'
        "| mark | tier | meaning |\n|---|---|---|\n" + rows + "\n"
    )


def build_md() -> str:
    """The committed catalogue.

    Deliberately **environment-independent**: no timestamp, no Python/platform line, verdicts read
    the declared dependencies rather than the installed state. The measured outcomes still depend on
    the optional extras, so regenerate it with the full extra set and let CI check it there.
    """
    runs = _collect()
    unexpected = behavior_failures()
    parts = [
        "# uniparser2 parsing-chain report",
        "",
        "Input → triple chain → output repr: every entry below is the result of a **real run** "
        "(`uv run python tools/demo_report.py --md`). This file is generated — regenerate it "
        "after changing an operator; `--md --check` fails when it is stale. The local HTML build "
        "(`.cache/report/up2-report.html`) shows installed/missing dependency state and is not "
        "committed.",
        "",
        f"Generated from `uniparser2` {up2.__version__} · one case per `(operator, action)` pair "
        "declared by the registry, plus multi-stage compositions, the shared mechanisms and the "
        "compile-time invalid forms.",
        "",
        _md_coverage(runs, unexpected),
        _md_tier_legend(),
    ]
    for item, cases, chains, bad in runs.sections():
        parts.append(_md_section(item, cases, chains, bad))
    parts += [
        "## Appendix: mechanisms shared by all operators",
        "",
        "These are **not grouped by operator**: the tri-state, the policy and the parameter forms "
        "belong to every operator, so slicing them per operator would hide the differences.",
        "",
        "### A. Tri-state and policy",
        "",
        'The defaults are `on_missing=empty` and `on_error=raise`, so "no match" falls back to '
        '`Ok("")` unless the policy says otherwise.',
        "",
    ]
    for ran in runs.edges:
        parts.append(_md_case(ran, None, shared_input=""))
    parts += [
        "### B. Parameter forms",
        "",
        "The scalar / positional array / named object / reference / directive forms of the "
        "parameter slot.",
        "",
    ]
    for ran in runs.forms:
        parts.append(_md_case(ran, None, shared_input=""))
    parts += ["### C. Invalid forms owned by no operator", "", _md_bad_table(runs.orphan_bad())]
    return "\n".join(parts).rstrip() + "\n"


_CSS: Final = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { margin: 0 auto; max-width: 1180px; padding: 24px 20px 64px;
  font: 15px/1.6 -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif; }
h1 { font-size: 24px; margin: 0 0 4px; }
h2 { font-size: 19px; margin: 34px 0 2px; padding-bottom: 6px; border-bottom: 2px solid #8884; }
h3 { font-size: 15px; margin: 20px 0 6px; color: #666; }
section.op { padding-top: 6px; }
p.sub { margin: 6px 0 12px; color: #777; font-size: 13px; }
pre, code { font-family: ui-monospace, Consolas, "Courier New", monospace; font-size: 12.5px; }
pre { margin: 0; white-space: pre-wrap; word-break: break-word; }
.card { border: 1px solid #8883; border-radius: 8px; padding: 10px 12px; margin: 10px 0; }
.head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.pair { font-weight: 600; }
code.summary { color: #888; font-weight: 400; }
.note, .ref { color: #888; font-size: 12px; }
.warn { color: #c62828; font-size: 12px; }
.badge { font-size: 11px; padding: 2px 8px; border-radius: 999px; color: #fff; }
.badge.ok { background: #2e7d32; } .badge.miss { background: #b8860b; }
.badge.fail { background: #c62828; } .badge.err { background: #6a1b9a; }
.tier { font-size: 12px; color: #b8860b; letter-spacing: -1px; }
.io { display: grid; grid-template-columns: 76px 1fr; gap: 8px; margin: 4px 0; }
.label { color: #777; font-size: 12px; padding-top: 2px; }
pre.result { background: #8881; border-left: 3px solid #2e7d3255; padding: 4px 8px; }
.steps { display: grid; gap: 4px; }
.step { display: grid; grid-template-columns: 1fr 18px 1.2fr; gap: 6px; align-items: baseline; }
.step code { background: #8881; padding: 2px 6px; border-radius: 4px; }
.arrow { color: #999; text-align: center; }
code.out { background: #2e7d3218; }
details.doc { margin: 10px 0; border: 1px dashed #8884; border-radius: 8px; padding: 8px 10px; }
details.doc summary { cursor: pointer; color: #777; font-size: 13px; }
table { border-collapse: collapse; width: 100%; font-size: 13px; margin: 6px 0; }
th, td { border: 1px solid #8883; padding: 5px 8px; text-align: left; vertical-align: top; }
th { background: #8881; }
.toc a { display: inline-block; margin: 0 10px 6px 0; }
.banner { padding: 10px 12px; border-radius: 8px; margin: 12px 0; }
.banner.good { background: #2e7d3222; border: 1px solid #2e7d3266; }
.banner.bad { background: #c6282822; border: 1px solid #c6282866; }
.meta { color: #777; font-size: 12.5px; }
@media (prefers-color-scheme: dark) { body { background: #16181d; color: #e6e6e6; } }
"""


def behavior_failures() -> list[Ran]:
    """Every case of the "full behavior" set must produce ``Ok``; otherwise the fixture is
    wrong (the tri-state cases in the appendix are excluded).

    This self-check once caught a real bug: a chain for the attribute action wrongly used the
    placeholder name, so the attribute was not found and an empty string came back silently. The
    multi-stage compositions are checked too — a composition that ends ``Failed`` demonstrates
    nothing but the failure (the ``css → code`` case used ``css``, which yields a *list*, so the
    sandbox function that needs a string rejected it).
    """
    cases = [*coverage_cases(), *chain_cases()]
    return [ran for ran in (_run(case) for case in cases) if ran.state != "Ok"]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render the parsing-chain report from real runs.")
    parser.add_argument(
        "--md",
        action="store_true",
        help=f"render the Markdown catalogue for the repository (default {MD_PATH}) "
        "instead of the local HTML",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    target = MD_PATH if args.md else OUT_PATH
    text = build_md() if args.md else build_html()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="\n")
    print(f"Wrote {target.resolve()} ({target.stat().st_size / 1024:.0f} KB)")
    failures = behavior_failures()
    if failures:
        names = ", ".join(f"{ran.case.op}.{ran.case.action}" for ran in failures)
        print(
            f"warning: {len(failures)} behavior cases are not Ok (a fixture may be wrong): {names}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
