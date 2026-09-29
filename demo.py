"""uniparser2 walkthrough demo: **input → chain → output**, one section per operator.

Run:

    uv run python demo.py

Every section prints the real chains it ran and the real outcome, so the file doubles as a
cheat-sheet: 10 operators, the tri-state settlement, and what a bad chain looks like.

How to read a chain stage (**one rule for every operator**):

- **Slot 2 = action**: the action enumeration declared by that operator (`text` / `@href` /
  `search` / `get`…), or the function name for `py` / `udf`
- **Slot 3 = parameter**: the data this stage operates on (CSS selector / XPath / regex /
  function argument)
- **An operator with a single action takes only two positions**: ``["json", "data.html"]`` /
  ``["const", "article"]``

Example: ``["css1", "@href", "a.download"]`` = the css1 "attribute" action on ``a.download``.
``$globals.x`` inside a parameter is a **reference** (``$`` means "read from the scope").

Optional engines are declared per operator: if an extra is missing (``lxml`` / ``jmespath`` /
``pydantic_monty``), the compile step reports ``UP2-E1107`` with the install command instead of
crashing, and the section below says so.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Final

import uniparser2 as up2

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

# One field = one field chain; a stage = [operator, action, parameter].
HTML_CHAINS: dict[str, Any] = {
    "title": [["css1", "text", "h1.article-title"], ["py", "normalize_space", ""]],
    "pub_time": [["css1", "@content", "meta[name=PubDate]"], ["py", "parse_time", ""]],
    "pdf_url": [["css1", "@href", "a.download"], ["py", "urljoin", BASE_URL]],
    "rel_count": [["css", "nodes", "ul.rel a"], ["py", "len", ""]],
    "rel_links": [["css", "@href", "ul.rel a"]],
    "content": [
        ["css", "remove", "script,style"],  # pure function: returns a pruned copy
        ["css1", "html", "div.content"],  # first match only ⇒ scalar
        ["py", "html_to_markdown", ""],
    ],
}

# XML uses the xpath operator (lxml); the sitemap has a default namespace, hence local-name().
XML_CHAINS: dict[str, Any] = {
    "sitemap_urls": [["xpath", "text", "//*[local-name()='loc']"]],
    "sitemap_count": [["xpath", "nodes", "//*[local-name()='url']"], ["py", "len", ""]],
    "sitemap_last": [["xpath", "text", "//*[local-name()='lastmod']"], ["py", "first", ""]],
}

# RSS 2.0: CDATA bodies, RFC 822 dates, and two namespaced extensions (dc:, content:).
SAMPLE_RSS2 = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/"
     xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>Gov Notices</title>
    <item>
      <title><![CDATA[Notice on <b>Service Items</b>]]></title>
      <link>https://www.example.gov.cn/p/1.html</link>
      <pubDate>Thu, 24 Sep 2026 15:30:00 +0800</pubDate>
      <guid isPermaLink="false">notice-1</guid>
      <dc:creator>Reporter A</dc:creator>
      <description><![CDATA[<p>To all <b>municipal</b> governments:</p>]]></description>
      <content:encoded><![CDATA[<div><p>Full body.</p></div>]]></content:encoded>
    </item>
    <item>
      <title>Plain second item</title>
      <link>https://www.example.gov.cn/p/2.html</link>
      <pubDate>Fri, 25 Sep 2026 09:00:00 +0800</pubDate>
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

# Multi-match operators return a list, so single-value functions need `py.first` first; a
# namespaced element is reached with local-name(), a namespaced *attribute* with @*[local-name()].
RSS2_CHAINS: dict[str, Any] = {
    "feed_title": [
        ["xpath", "text", "//*[local-name()='channel']/*[local-name()='title']"],
        ["py", "first", ""],
    ],
    "item_count": [["xpath", "nodes", "//*[local-name()='item']"], ["py", "len", ""]],
    "item_titles": [["xpath", "text", "//*[local-name()='item']/*[local-name()='title']"]],
    "first_title": [
        ["xpath", "text", "//*[local-name()='item']/*[local-name()='title']"],
        ["py", "first", ""],
        ["py", "strip_tags", ""],
    ],
    "first_link": [["xpath", "text", "//*[local-name()='link']"], ["py", "first", ""]],
    "first_pub_date": [
        ["xpath", "text", "//*[local-name()='pubDate']"],
        ["py", "first", ""],
        ["py", "parse_time", ""],
    ],
    "first_creator": [["xpath", "text", "//*[local-name()='creator']"], ["py", "first", ""]],
    "guid_is_permalink": [
        ["xpath", "text", "//*[local-name()='guid']/@isPermaLink"],
        ["py", "first", ""],
    ],
    "first_description_md": [
        ["xpath", "text", "//*[local-name()='description']"],
        ["py", "first", ""],
        ["py", "html_to_markdown", ""],
    ],
    "first_content_md": [
        ["xpath", "text", "//*[local-name()='encoded']"],
        ["py", "first", ""],
        ["py", "html_to_markdown", ""],
    ],
}

ATOM_CHAINS: dict[str, Any] = {
    "entry_title": [
        ["xpath", "text", "//*[local-name()='entry']/*[local-name()='title']"],
        ["py", "first", ""],
    ],
    "entry_link": [["xpath", "text", "//*[local-name()='link']/@href"], ["py", "first", ""]],
    "entry_updated": [
        ["xpath", "text", "//*[local-name()='updated']"],
        ["py", "first", ""],
        ["py", "parse_time", {"lang": "en"}],
    ],
    "entry_summary": [
        ["xpath", "text", "//*[local-name()='summary']"],
        ["py", "first", ""],
        ["py", "strip_tags", ""],
    ],
    "entry_summary_md": [
        ["xpath", "text", "//*[local-name()='summary']"],
        ["py", "first", ""],
        ["py", "html_to_markdown", ""],
    ],
}

RDF_CHAINS: dict[str, Any] = {
    "item_about": [
        ["xpath", "text", "//*[local-name()='item']/@*[local-name()='about']"],
        ["py", "first", ""],
    ],
    "item_title": [
        ["xpath", "text", "//*[local-name()='item']/*[local-name()='title']"],
        ["py", "first", ""],
    ],
    "item_date": [
        ["xpath", "text", "//*[local-name()='date']"],
        ["py", "first", ""],
        ["py", "parse_time", ""],
    ],
}

FEED_DOCS: tuple[tuple[str, str, dict[str, Any]], ...] = (
    ("RSS 2.0 — CDATA, RFC 822 dates, dc:/content: extensions", SAMPLE_RSS2, RSS2_CHAINS),
    ("Atom 1.0 — default namespace, attribute links, ISO 8601", SAMPLE_ATOM, ATOM_CHAINS),
    ("RSS 1.0 / RDF — rdf:about, dc:date", SAMPLE_RDF, RDF_CHAINS),
)

# The settlement policy: what a field becomes when the value is absent or the rule is broken.
POLICY = up2.Policy(on_missing="drop")
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
    if isinstance(outcome, up2.Missing):
        return f"Missing ({outcome.reason})" if outcome.reason else "Missing"
    return f"{outcome.code} {outcome.reason}"


def heading(title: str) -> None:
    print("\n" + "=" * 76)
    print(title)
    print("=" * 76)


def show_source(title: str, source: str) -> None:
    heading(title)
    print(source.strip())


def run(chain: list[Any], value: Any, *, policy: up2.Policy = POLICY) -> up2.Outcome:
    """Compile + evaluate one chain on a fresh scope; remember which operators it used."""
    for step in chain:
        SHOWN.add(step[0])
    return up2.eval_field(up2.compile_field(chain), value, scope=make_scope(), policy=policy)


def one(label: str, chain: list[Any], value: Any, *, policy: up2.Policy = POLICY) -> None:
    """Print a single chain and its outcome."""
    outcome = run(chain, value, policy=policy)
    print(f"   {json.dumps(chain, ensure_ascii=False)}")
    print(f"       {label}: {render_outcome(outcome)}")


def trace(name: str, chain: list[Any], source: str) -> None:
    """Print every rule a field went through with each stage's output, then the final output."""
    print(f"\n-- field {name} " + "-" * max(4, 46 - len(name)))
    width = max(len(json.dumps(step, ensure_ascii=False)) for step in chain)
    shown = ""
    for index in range(1, len(chain) + 1):
        outcome = run(chain[:index], source)
        shown = render_outcome(outcome)
        step = json.dumps(chain[index - 1], ensure_ascii=False)
        print(f"   {step:<{width}}  -> {shown}")
    print(f"   {'output':<{width}}  =  {shown}")


def section_selectors() -> None:
    show_source(
        "1. `css` / `css1` — CSS selectors on HTML (optional extra: selectolax)", SAMPLE_HTML
    )
    for name, chain in HTML_CHAINS.items():
        trace(name, chain, SAMPLE_HTML)
    print("\n   `css` returns every match, `css1` only the first one; `nodes`/`self` give handles,")
    print("   `text`/`html`/`outer`/`@<attribute>` turn a handle into text.")


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
    print("   `py.strip_tags` / `py.html_to_markdown`. Multi-match operators return a list, so a")
    print("   single-value function needs `py.first` first. A namespaced element is reached with")
    print("   `local-name()`; a namespaced *attribute* needs `@*[local-name()='about']` (`@about`")
    print("   misses it). `py.parse_time` reads both feed date shapes with no parameters (RFC 822")
    print("   and zone-bearing ISO 8601); the offset is consumed, so the wall clock is what comes")
    print('   back — use {"lang": "en"} for natural language, or {"format": ...} for the rest.')


def section_json() -> None:
    show_source("3. `json` — jmespath queries (optional extra: jmespath)", SAMPLE_JSON)
    one("the URLs of every list item", [["json", "data.list[*].url"]], SAMPLE_JSON)
    one("chain steps compose", [["json", "data.list[*].title"], ["py", "first", ""]], SAMPLE_JSON)
    one(
        "a JSON field may itself be HTML",
        [["json", "data.html"], ["py", "strip_tags", ""]],
        SAMPLE_JSON,
    )


def section_regex() -> None:
    show_source("4. `re` — regular expressions (no extra needed)", SAMPLE_TEXT)
    one("first date-like match", [["re", "search", r"\d{4}-\d{2}-\d{2}"]], "2026-09-24T15:30")
    one(
        "one capture group",
        [["re", "group", {"pattern": r"(\d{4})-(\d{2})", "group": 2}]],
        "2026-09-24",
    )
    one("all digit runs", [["re", "findall", r"\d+"]], SAMPLE_TEXT)
    one("match, then convert", [["re", "search", r"\d+"], ["py", "int", ""]], SAMPLE_TEXT)


def section_python() -> None:
    show_source("5. `py` — the 31-function allowlist (no extra needed)", SAMPLE_TEXT)
    one(
        "default() catches a Missing upstream",
        [["re", "search", r"\d+"], ["py", "default", "none"]],
        "abc",
    )
    one(
        "urljoin() reads a reference",
        [["css1", "@href", "a.download"], ["py", "urljoin", "$globals.base_url"]],
        SAMPLE_HTML,
    )
    one("split() + first()", [["py", "split", ","], ["py", "first", ""]], "a,b,c")
    one("replace()", [["py", "replace", {"old": "b22", "new": "B"}]], SAMPLE_TEXT)
    one("parse_time()", [["py", "parse_time", ""]], "2026-09-24 15:30:00")


def section_scope() -> None:
    heading("6. `ctx` — the scope: locals are writable, globals are read-only")
    one("set then get", [["ctx", "set", "locals.k"], ["ctx", "get", "locals.k"]], "kept")
    one(
        "map collects several paths",
        [["ctx", "set", "locals.k"], ["ctx", "map", {"a": "locals.k"}]],
        "v",
    )
    one(
        "del removes it again",
        [["ctx", "set", "locals.k"], ["ctx", "del", "locals.k"], ["ctx", "get", "locals.k"]],
        "v",
    )
    one("reading globals", [["ctx", "get", "globals.base_url"]], "ignored")
    print("\n   `ctx.set`/`del` may only write `locals`/`fields`; writing `globals` is UP2-E1015.")


def section_literals() -> None:
    heading("7. `const` — literals and build-up")
    one("a plain literal", [["const", "article"]], "ignored", policy=up2.Policy(on_missing="empty"))
    one("a literal that starts with $", [["const", {"$lit": "$not-a-reference"}]], "ignored")
    one(
        "const replaces the value mid-chain",
        [["css1", "text", "h1.article-title"], ["py", "normalize_space", ""], ["const", "fixed"]],
        SAMPLE_HTML,
    )
    one(
        "build-up: extract, store in locals, read it back",
        [
            ["css1", "text", "h1.article-title"],
            ["py", "normalize_space", ""],
            ["ctx", "set", "locals.title"],
            ["ctx", "get", "locals.title"],
        ],
        SAMPLE_HTML,
    )


def section_udf() -> None:
    heading("8. `udf` — host-registered functions (no code in the chain)")

    def shout(value: Any) -> str:
        return str(value).upper()

    def with_ctx(value: Any, ctx: Any) -> str:
        return f"{value}|{ctx.globals.base_url}|{ctx.locals.k}"

    up2.register_udf("demo_shout", shout)
    up2.register_udf("demo_with_ctx", with_ctx)
    one(
        "a plain function",
        [
            ["css1", "text", "h1.article-title"],
            ["py", "normalize_space", ""],
            ["udf", "demo_shout", ""],
        ],
        SAMPLE_HTML,
    )
    one(
        "a function that declares ctx",
        [["ctx", "set", "locals.k"], ["udf", "demo_with_ctx", ""]],
        "value",
    )
    print(
        '\n   Registering is the trust boundary: the chain holds only the name. `["udf","nope",""]`'
    )
    print("   fails at compile time with UP2-E1010.")


def section_code() -> None:
    heading(
        "9. `code` — in-chain code in a language-level sandbox (optional extra: pydantic-monty)"
    )
    one(
        "extract → normalise → store in locals → read it in code",
        [
            ["css1", "text", "h1.article-title"],
            ["py", "normalize_space", ""],
            ["ctx", "set", "locals.title"],
            ["code", {"src": "ctx.locals.title.upper()"}],
        ],
        SAMPLE_HTML,
    )
    one(
        "named inputs (checked at compile time)",
        [
            ["css1", "text", "h1.article-title"],
            ["code", {"src": "prefix + normalize_space(obj)", "inputs": {"prefix": "Title: "}}],
        ],
        SAMPLE_HTML,
    )
    one("the sandbox has no host capability", [["code", {"src": "import socket"}]], "x")
    one("a sandbox failure is a normal error", [["code", {"src": "1 / 0"}]], "x")
    print("   Defaults: 64 MB / 0.5 s per evaluation, frozen clock, seeded random; limits live on")
    print("   the host side (uniparser2.ops.code.configure) and the chain cannot widen them.")


def section_policy() -> None:
    heading("10. Tri-state and policy — what an absent or broken value settles to")
    chain = [["re", "search", r"\d+"]]
    for missing in ("empty", "none", "drop", "raise"):
        one(f"on_missing={missing}", chain, "abc", policy=up2.Policy(on_missing=missing))
    one("a broken rule is an error by default", [["py", "int", ""]], "abc")
    one(
        "...unless you downgrade it",
        [["py", "int", ""]],
        "abc",
        policy=up2.Policy(on_error="empty"),
    )


def section_diagnostics() -> None:
    heading("11. Diagnostics — bad chains fail at compile time, with a code and a JSON Pointer")
    bad_chains: list[tuple[str, list[Any]]] = [
        ("wrong arity", [["py", "replace", "old,new", "extra"]]),
        ("unknown action", [["css", "innerHTML", "h1"]]),
        ("dangling reference", [["const", "$nope.x"]]),
        ("a reference to a non-writable root", [["ctx", "set", "globals.x"]]),
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


SECTIONS: Final[tuple[tuple[str, Callable[[], None]], ...]] = (
    ("css / css1", section_selectors),
    ("xpath", section_xpath),
    ("json", section_json),
    ("re", section_regex),
    ("py", section_python),
    ("ctx", section_scope),
    ("const", section_literals),
    ("udf", section_udf),
    ("code", section_code),
    ("policy", section_policy),
    ("diagnostics", section_diagnostics),
)
ALL_OPERATORS: Final = frozenset(
    {"css", "css1", "py", "xpath", "json", "re", "ctx", "const", "code", "udf"}
)


def main() -> None:
    for _, section in SECTIONS:
        try:
            section()
        except up2.Up2Error as exc:  # an optional engine is missing: report it and move on
            print(f"   skipped: {exc.diagnostic.code} {exc.diagnostic.message}")

    heading("Covered in this run")
    shown = SHOWN & ALL_OPERATORS
    print(f"   operators exercised: {len(shown)}/{len(ALL_OPERATORS)}")
    print(f"   -> {', '.join(sorted(shown))}")
    if ALL_OPERATORS - SHOWN:
        skipped = ", ".join(sorted(ALL_OPERATORS - SHOWN))
        print(f"   not exercised (optional engine missing): {skipped}")


if __name__ == "__main__":
    main()
