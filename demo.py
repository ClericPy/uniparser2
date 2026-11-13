"""uniparser2 walkthrough demo: **input → chain → output**, one section per operator.

Run:

    uv run python demo.py

Every section prints the real chains it ran and the real outcome, so the file doubles as a
cheat-sheet: 12 operators, the outcome model, and what a bad chain looks like.

How to read a chain stage (**one rule for every operator**):

- **Slot 2 = action**: the action enumeration declared by that operator (`text` / `@href` /
  `search` / `get`…), or the function name for `py` / `udf`
- **Slot 3 = parameter**: the data this stage operates on (CSS selector / XPath / regex /
  function argument); it is **omitted** when nothing required remains (`["py","strip"]`)

Example: ``["css1", "@href", "a.download"]`` = the css1 "attribute" action on ``a.download``.
``$globals.x`` inside a parameter is a **reference** (``$`` means "read from the scope").

Optional engines are declared per operator: if an extra is missing (``lxml`` / ``jmespath`` /
``pydantic_monty``), the compile step reports ``UP2-E1107`` with the install command instead of
crashing, and that one chain is skipped.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final

import uniparser2 as up2
from uniparser2.core import registry

SAMPLE_HTML = """
<html>
  <head><meta name="PubDate" content="2026-09-24 15:30:00"></head>
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

SAMPLE_SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://www.example.gov.cn/p/1.html</loc><lastmod>2026-09-23</lastmod></url>
  <url><loc>https://www.example.gov.cn/p/2.html</loc><lastmod>2026-09-24</lastmod></url>
</urlset>
"""

SAMPLE_JSON = json.dumps(
    {
        "data": {
            "list": [
                {"url": "https://www.example.gov.cn/p/1.html", "title": "Related one"},
                {"url": "https://www.example.gov.cn/p/2.html", "title": "Related two"},
            ],
            "html": "<p>a fragment that arrived as a JSON field</p>",
        }
    },
    ensure_ascii=False,
)

SAMPLE_TEXT = "a1b22c333"
BASE_URL = "https://www.example.gov.cn/public/"

# One field = one field chain; a stage is [operator, action, parameter].
HTML_CHAINS: dict[str, Any] = {
    "title": [["css1", "text", "h1.article-title"], ["py", "normalize_space"]],
    "pub_time": [
        ["css1", "@content", "meta[name=PubDate]"],
        ["py", "strptime", "%Y-%m-%d %H:%M:%S"],
        ["py", "strftime", "%Y-%m-%d"],
    ],
    "pdf_url": [["css1", "@href", "a.download"], ["py", "urljoin", BASE_URL]],
    "rel_count": [["css", "nodes", "ul.rel a"], ["py", "len"]],
    "rel_links": [["css", "@href", "ul.rel a"]],
    "has_download": [["css", "exists", "a.download"]],
    "content": [
        ["css", "remove", "script,style"],  # pure function: returns a pruned copy
        ["css1", "html", "div.content"],  # first match only ⇒ scalar
        ["py", "html_to_markdown"],
    ],
}

# XML uses the xpath operator (lxml); the sitemap has a default namespace, hence local-name().
XML_CHAINS: dict[str, Any] = {
    "sitemap_urls": [["xpath", "text", "//*[local-name()='loc']"]],
    "sitemap_count": [
        ["xpath", "text", "count(//*[local-name()='url'])"],
        ["py", "first"],
    ],
    "sitemap_last": [["xpath", "text", "//*[local-name()='lastmod']"], ["py", "last"]],
}

# RSS 2.0: CDATA bodies, ISO dates, and two namespaced extensions (dc:, content:).
SAMPLE_RSS2 = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/"
     xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>Gov Notices</title>
    <item>
      <title><![CDATA[Notice on <b>Service Items</b>]]></title>
      <link>https://www.example.gov.cn/p/1.html</link>
      <pubDate>2026-09-24T15:30:00+08:00</pubDate>
      <guid isPermaLink="false">notice-1</guid>
      <dc:creator>Reporter A</dc:creator>
      <description><![CDATA[<p>To all <b>municipal</b> governments:</p>]]></description>
      <content:encoded><![CDATA[<div><p>Full body.</p></div>]]></content:encoded>
    </item>
    <item>
      <title>Plain second item</title>
      <link>https://www.example.gov.cn/p/2.html</link>
      <pubDate>2026-09-25T09:00:00+08:00</pubDate>
      <guid>notice-2</guid>
    </item>
  </channel>
</rss>
"""

# Atom 1.0: the feed element carries a default namespace; links are attributes; dates are ISO 8601.
SAMPLE_ATOM = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Gov Notices</title>
  <entry>
    <id>urn:uuid:notice-1</id>
    <title>Notice on Service Items</title>
    <link rel="alternate" type="text/html" href="https://www.example.gov.cn/p/1.html"/>
    <updated>2026-09-24T15:30:00Z</updated>
    <summary type="html">&lt;p&gt;Escaped &lt;b&gt;HTML&lt;/b&gt; summary&lt;/p&gt;</summary>
  </entry>
</feed>
"""

# RSS 1.0 (RDF): items are siblings of the channel and carry rdf:about.
SAMPLE_RDF = """<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns="http://purl.org/rss/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel rdf:about="https://www.example.gov.cn/rss.xml"><title>Gov Notices</title></channel>
  <item rdf:about="https://www.example.gov.cn/p/1.html">
    <title>RDF item one</title>
    <dc:date>2026-09-24</dc:date>
  </item>
</rdf:RDF>
"""

_STRIP_TAGS: Final = ["re", "sub", [r"<[^>]+>", ""]]

# Multi-match operators return a list, so single-value functions need `py.first` first; a
# namespaced element is reached with local-name(), a namespaced *attribute* with @*[local-name()].
RSS2_CHAINS: dict[str, Any] = {
    "feed_title": [
        ["xpath", "text", "//*[local-name()='channel']/*[local-name()='title']"],
        ["py", "first"],
    ],
    "item_count": [["xpath", "nodes", "//*[local-name()='item']"], ["py", "len"]],
    "item_titles": [["xpath", "text", "//*[local-name()='item']/*[local-name()='title']"]],
    "first_title": [
        ["xpath", "text", "//*[local-name()='item']/*[local-name()='title']"],
        ["py", "first"],
        _STRIP_TAGS,
        ["py", "normalize_space"],
    ],
    "first_link": [["xpath", "text", "//*[local-name()='link']"], ["py", "first"]],
    "first_pub_date": [
        ["xpath", "text", "//*[local-name()='pubDate']"],
        ["py", "first"],
        ["py", "strptime", "%Y-%m-%dT%H:%M:%S%z"],
        ["py", "strftime", "%Y-%m-%d %H:%M"],
    ],
    "first_creator": [["xpath", "text", "//*[local-name()='creator']"], ["py", "first"]],
    "guid_is_permalink": [
        ["xpath", "text", "//*[local-name()='guid']/@isPermaLink"],
        ["py", "first"],
    ],
    "first_description": [
        ["xpath", "text", "//*[local-name()='description']"],
        ["py", "first"],
        _STRIP_TAGS,
        ["py", "normalize_space"],
    ],
    "first_content_md": [
        ["xpath", "text", "//*[local-name()='encoded']"],
        ["py", "first"],
        ["py", "html_to_markdown"],
    ],
}

ATOM_CHAINS: dict[str, Any] = {
    "entry_title": [
        ["xpath", "text", "//*[local-name()='entry']/*[local-name()='title']"],
        ["py", "first"],
    ],
    "entry_link": [["xpath", "text", "//*[local-name()='link']/@href"], ["py", "first"]],
    "entry_updated": [
        ["xpath", "text", "//*[local-name()='updated']"],
        ["py", "first"],
        ["py", "strptime", "%Y-%m-%dT%H:%M:%S%z"],
        ["py", "strftime", "%Y-%m-%d %H:%M"],
    ],
    "entry_summary": [
        ["xpath", "text", "//*[local-name()='summary']"],
        ["py", "first"],
        _STRIP_TAGS,
        ["py", "normalize_space"],
    ],
    "entry_summary_md": [
        ["xpath", "text", "//*[local-name()='summary']"],
        ["py", "first"],
        ["py", "html_to_markdown"],
    ],
}

RDF_CHAINS: dict[str, Any] = {
    "item_about": [
        ["xpath", "text", "//*[local-name()='item']/@*[local-name()='about']"],
        ["py", "first"],
    ],
    "item_title": [
        ["xpath", "text", "//*[local-name()='item']/*[local-name()='title']"],
        ["py", "first"],
    ],
    "item_date": [
        ["xpath", "text", "//*[local-name()='date']"],
        ["py", "first"],
        ["py", "strptime", "%Y-%m-%d"],
        ["py", "strftime", "%Y/%m/%d"],
    ],
}

FEED_DOCS: tuple[tuple[str, str, dict[str, Any]], ...] = (
    ("RSS 2.0 — CDATA, ISO dates, dc:/content: extensions", SAMPLE_RSS2, RSS2_CHAINS),
    ("Atom 1.0 — default namespace, attribute links, ISO 8601", SAMPLE_ATOM, ATOM_CHAINS),
    ("RSS 1.0 / RDF — rdf:about, dc:date", SAMPLE_RDF, RDF_CHAINS),
)

# The outcome model is fixed: a query that matches nothing is an empty value, and a failed stage
# always fails the run.
_LIMIT = 62
SHOWN: set[str] = set()


def make_scope() -> up2.Scope:
    """A fresh scope per example, so one section cannot leak state into the next."""
    return up2.Scope(globals={"base_url": BASE_URL})


def render(value: Any) -> str:
    """Render a value: handles are reported by count only, long results are truncated."""
    if isinstance(value, up2.Opaque):
        return f"<{type(value).__name__} handle>"
    if isinstance(value, list) and value and all(isinstance(item, up2.Opaque) for item in value):
        return f"<{len(value)} node handles>"
    text = repr(value)
    return text if len(text) <= _LIMIT else text[:_LIMIT] + "..."


def render_outcome(outcome: up2.Outcome) -> str:
    if isinstance(outcome, up2.Ok):
        return render(outcome.value)
    return f"{outcome.code} {outcome.reason}"


def heading(title: str) -> None:
    print("\n" + "=" * 76)
    print(title)
    print("=" * 76)


def show_source(title: str, source: str) -> None:
    heading(title)
    print(source.strip())


def _skippable(exc: up2.Up2Error) -> bool:
    """A missing optional engine skips one chain; anything else is a real failure."""
    return exc.diagnostic.code == "UP2-E1107"


def run(chain: list[Any], value: Any) -> up2.Outcome:
    """Compile + evaluate one chain on a fresh scope; remember which operators it used.

    The operators are recorded only after the whole chain compiled, so a chain skipped for a
    missing optional engine does not count as exercised.
    """
    compiled = up2.compile_field(chain)
    for stage in chain:
        SHOWN.add(stage[0])
    return up2.eval_field(compiled, value, scope=make_scope())


def one(label: str, chain: list[Any], value: Any) -> None:
    """Print a single chain and its outcome."""
    print(f"   {json.dumps(chain, ensure_ascii=False)}")
    try:
        outcome = run(chain, value)
    except up2.Up2Error as exc:
        if _skippable(exc):
            print(f"       skipped: {exc.diagnostic.code} {exc.diagnostic.message}")
            print(f"       fix: {exc.diagnostic.fix}")
            return
        raise
    print(f"       {label}: {render_outcome(outcome)}")


def trace(name: str, chain: list[Any], source: Any) -> None:
    """Print every rule a field went through with each stage's output, then the final output."""
    print(f"\n-- field {name} " + "-" * max(4, 46 - len(name)))
    width = max(len(json.dumps(step, ensure_ascii=False)) for step in chain)
    shown = ""
    try:
        for index in range(1, len(chain) + 1):
            outcome = run(chain[:index], source)
            shown = render_outcome(outcome)
            step = json.dumps(chain[index - 1], ensure_ascii=False)
            print(f"   {step:<{width}}  -> {shown}")
    except up2.Up2Error as exc:
        if _skippable(exc):
            print(f"   skipped: {exc.diagnostic.code} {exc.diagnostic.message}")
            print(f"       fix: {exc.diagnostic.fix}")
            return
        raise
    print(f"   {'output':<{width}}  =  {shown}")


def section_selectors() -> None:
    show_source(
        "1. `css` / `css1` — CSS selectors on HTML (optional extra: selectolax)", SAMPLE_HTML
    )
    for name, chain in HTML_CHAINS.items():
        trace(name, chain, SAMPLE_HTML)
    print("\n   `css` returns every match, `css1` only the first one; `nodes`/`self` give handles,")
    print("   `text`/`html`/`outer`/`@<attribute>` turn a handle into text, and `exists` answers a")
    print("   boolean for a decision.")


def section_xpath() -> None:
    show_source(
        "2. `xpath` — XML: sitemap, RSS 2.0, Atom, RDF (optional extra: lxml)", SAMPLE_SITEMAP
    )
    for name, chain in XML_CHAINS.items():
        trace(name, chain, SAMPLE_SITEMAP)
    for title, source, chains in FEED_DOCS:
        show_source(title, source)
        for name, chain in chains.items():
            trace(name, chain, source)
    print("\n   Reading real feeds: a CDATA section is just text — HTML inside it still needs")
    print("   `re.sub` or `py.html_to_markdown`. Multi-match operators return a list, so a")
    print("   single-value function needs `py.first` first. A namespaced element is reached with")
    print("   `local-name()`; a namespaced *attribute* needs `@*[local-name()='about']`.")
    print("   The dates here are ISO; an RFC 822 date needs a host `udf` or `code`, because")
    print("   `%a` / `%b` are locale-dependent and rejected by `strptime` (design D6).")


def section_json() -> None:
    show_source("3. `json` — jmespath queries (optional extra: jmespath)", SAMPLE_JSON)
    one("the URLs of every list item", [["json", "data.list[*].url"]], SAMPLE_JSON)
    one("chain steps compose", [["json", "data.list[*].title"], ["py", "first"]], SAMPLE_JSON)
    one(
        "a JSON field may itself be HTML",
        [["json", "data.html"], ["py", "html_to_markdown"]],
        SAMPLE_JSON,
    )


def section_regex() -> None:
    show_source("4. `re` — regular expressions (no extra needed)", SAMPLE_TEXT)
    one("first date-like match", [["re", "search", r"\d{4}-\d{2}-\d{2}"]], "2026-09-24T15:30")
    one("one capture group", [["re", "search", [r"(\d{4})-(\d{2})", 2]]], "2026-09-24")
    one("every digit run", [["re", "findall", r"\d+"]], SAMPLE_TEXT)
    one("replace every run", [["re", "sub", [r"\d+", "#"]]], SAMPLE_TEXT)
    one("match, then convert", [["re", "search", r"\d+"], ["py", "int"]], SAMPLE_TEXT)


def section_python() -> None:
    show_source("5. `py` — the 48-function allowlist (no extra needed)", SAMPLE_TEXT)
    one(
        "or() is the fallback for an empty stage value",
        [["re", "search", r"\d+"], ["py", "or", ["none"]]],
        "abc",
    )
    one(
        "urljoin() reads a reference",
        [["css1", "@href", "a.download"], ["py", "urljoin", "$globals.base_url"]],
        SAMPLE_HTML,
    )
    one("split() + first()", [["py", "split", ","], ["py", "first"]], "a,b,c")
    one("replace() takes one positional array", [["py", "replace", ["b22", "B"]]], SAMPLE_TEXT)
    one(
        "strptime() → strftime()",
        [
            ["py", "strptime", "%Y-%m-%d %H:%M:%S"],
            ["py", "strftime", "%Y/%m/%d"],
        ],
        "2026-09-24 15:30:00",
    )
    one(
        "from_timestamp() → strftime()",
        [["py", "from_timestamp", 8], ["py", "strftime", "%Y-%m-%d %H:%M:%S"]],
        0,
    )
    one(
        "in() — a predicate, spelled the way Python spells it",
        [["py", "in", [200, 301, 302]]],
        301,
    )
    one("between() is half-open", [["py", "between", [200, 300]]], 250)


def section_scope() -> None:
    heading("6. `ctx` — the scope: locals and public are writable, globals are read-only")
    one("set then get", [["ctx", "set", "locals.k"], ["ctx", "get", "locals.k"]], "kept")
    one(
        "dict collects several paths",
        [["ctx", "set", "locals.k"], ["ctx", "dict", {"a": "locals.k"}]],
        "v",
    )
    one(
        "list collects several paths",
        [["ctx", "set", "locals.k"], ["ctx", "list", ["locals.k"]]],
        "v",
    )
    one(
        "del removes it again",
        [["ctx", "set", "locals.k"], ["ctx", "del", "locals.k"], ["ctx", "get", "locals.k"]],
        "v",
    )
    one("reading globals", [["ctx", "get", "globals.base_url"]], "ignored")
    print("\n   `ctx.set`/`del` may only write `locals`/`public`; writing `globals` is UP2-E1015.")


def section_literals() -> None:
    heading("7. `py.const` — literals and build-up")
    one("a plain literal", [["py", "const", "article"]], "ignored")
    one("a literal that starts with $", [["py", "const", {"$lit": "$not-a-reference"}]], "ignored")
    one(
        "const replaces the value mid-chain",
        [["css1", "text", "h1.article-title"], ["py", "normalize_space"], ["py", "const", "fixed"]],
        SAMPLE_HTML,
    )
    one(
        "build-up: extract, store in locals, read it back",
        [
            ["css1", "text", "h1.article-title"],
            ["py", "normalize_space"],
            ["ctx", "set", "locals.title"],
            ["ctx", "get", "locals.title"],
        ],
        SAMPLE_HTML,
    )


def section_udf() -> None:
    heading("8. `udf` — host-registered functions (no code in the chain)")

    def shout(value: Any) -> str:
        return str(value).upper()

    def join_two(left: Any, right: Any) -> str:
        return f"{left}+{right}"

    up2.register_udf("demo_shout", shout)
    up2.register_udf("demo_join", join_two)
    one(
        "a plain function",
        [
            ["css1", "text", "h1.article-title"],
            ["py", "normalize_space"],
            ["udf", "demo_shout"],
        ],
        SAMPLE_HTML,
    )
    one("the `*` form spreads a list", [["udf", "demo_join", "*"]], ["a", "b"])
    print('\n   Registering is the trust boundary: the chain holds only the name. `["udf","nope"]`')
    print("   fails at compile time with UP2-E1010.")


def section_code() -> None:
    heading(
        "9. `code` — in-chain code in a language-level sandbox (optional extra: pydantic-monty)"
    )
    one(
        "extract → normalise → store in locals → read it in code",
        [
            ["css1", "text", "h1.article-title"],
            ["py", "normalize_space"],
            ["ctx", "set", "locals.title"],
            ["code", "ctx.locals.title.upper()"],
        ],
        SAMPLE_HTML,
    )
    one("the sandbox mounts the pure py functions", [["code", "normalize_space(obj)"]], "  a  b  ")
    one("the sandbox has no host capability", [["code", "import socket"]], "x")
    one("a sandbox failure is a normal error", [["code", "1 / 0"]], "x")
    print("   Defaults: 64 MB / 0.5 s per evaluation, frozen clock, seeded random; limits live on")
    print("   the host side (uniparser2.ops.code.configure) and the chain cannot widen them.")


def section_tristate() -> None:
    heading("10. Outcomes — what an absent or broken value means")
    one(
        "a query that matched nothing is an empty value, not an error",
        [["re", "search", r"\d+"]],
        "abc",
    )
    one("a broken rule always fails the run", [["py", "int"]], "abc")
    one(
        "the failure stops the chain at the stage that failed",
        [["py", "int"], ["py", "strip"]],
        "abc",
    )
    one(
        "or() gives an empty stage value a fallback",
        [["re", "search", r"\d+"], ["py", "or", ["0"]]],
        "abc",
    )
    print('\n   There is no third state: `""` / `[]` / `null` are ordinary values, and everything')
    print("   else fails with a code.")


def section_diagnostics() -> None:
    heading("11. Diagnostics — bad chains fail at compile time, with a code and a JSON Pointer")
    bad_chains: list[tuple[str, list[Any]]] = [
        ("wrong arity", [["py", "replace", "old,new", "extra"]]),
        ("unknown action", [["css", "innerHTML", "h1"]]),
        ("dangling reference", [["py", "getitem", "$nope.x"]]),
        ("a reference to a non-writable root", [["ctx", "set", "globals.x"]]),
        ("an empty path segment", [["ctx", "get", "locals..x"]]),
        ("a ReDoS-shaped regular expression", [["re", "search", "(a+)+$"]]),
    ]
    for label, chain in bad_chains:
        try:
            up2.compile_field(chain)
        except up2.Up2Error as exc:
            diagnostic = exc.diagnostic
            print(f"   {label:<38} {diagnostic.code} at {diagnostic.pointer}")
            print(f"       {diagnostic.message}")
            if diagnostic.fix:
                print(f"       fix: {diagnostic.fix}")


def section_iteration() -> None:
    heading("12. `each` — one dictionary per element of a list")
    one(
        "a node set becomes one record per item",
        [
            ["css", "nodes", "ul.rel li"],
            ["each", {"title": [["css1", "text", "a"]], "href": [["css1", "@href", "a"]]}],
        ],
        SAMPLE_HTML,
    )
    one(
        "no engine needed: a list of strings",
        [["each", {"raw": [["py", "strip"]]}]],
        ["  a  ", "bb"],
    )
    one(
        "a `_`-prefixed field is a per-element temporary, not a key",
        [["each", {"_raw": [["py", "strip"]], "seen": [["ctx", "get", "locals._raw"]]}]],
        ["  a  ", "bb"],
    )
    one(
        "nested each stages iterate level by level",
        [["each", {"lens": [["each", {"n": [["py", "len"]]}]]}]],
        [["a", "b"], ["c"]],
    )


def section_story() -> None:
    heading("13. `node` / `type` — a story: nodes calling nodes, and a constructed type")

    @dataclass(slots=True)
    class DemoBook:
        title: str
        price: str

    story = {
        "nodes": {
            "record": [
                ["node", "fields"],
                ["type", "DemoBook"],
                ["py", "getattr", "title"],
            ],
            "fields": {
                "title": [["py", "getitem", "title"], ["py", "strip"]],
                "price": [["py", "getitem", "price"], ["py", "strip"]],
            },
        }
    }
    up2.register_type("DemoBook", DemoBook)
    try:
        product = up2.run(story, "record", {"title": "  A  ", "price": "12.00"})
    finally:
        up2.unregister_type("DemoBook")
    print("   story.nodes =", ", ".join(story["nodes"]))
    print('   run(story, "record", {...}) ->', render(product))
    print("   the `type` stage built a DemoBook and the next stage read its title.")
    SHOWN.update({"node", "type"})


SECTIONS: Final[tuple[tuple[str, Callable[[], None]], ...]] = (
    ("css / css1", section_selectors),
    ("xpath", section_xpath),
    ("json", section_json),
    ("re", section_regex),
    ("py", section_python),
    ("ctx", section_scope),
    ("py.const", section_literals),
    ("udf", section_udf),
    ("code", section_code),
    ("tri-state", section_tristate),
    ("diagnostics", section_diagnostics),
    ("each", section_iteration),
    ("story", section_story),
)


def main() -> int:
    failed = False
    for name, section in SECTIONS:
        try:
            section()
        except up2.Up2Error as exc:
            if _skippable(exc):
                print(f"   section {name} skipped: {exc.diagnostic.code} {exc.diagnostic.message}")
                continue
            print(f"   section {name} failed: {exc.diagnostic}", file=sys.stderr)
            failed = True

    heading("Covered in this run")
    declared = set(registry.canonical_names())
    shown = SHOWN & declared
    print(f"   operators exercised: {len(shown)}/{len(declared)}")
    print(f"   -> {', '.join(sorted(shown))}")
    if declared - shown:
        print(f"   not exercised: {', '.join(sorted(declared - shown))} (optional engine missing?)")
    if failed:
        print("   one or more sections failed; see the errors above.", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
