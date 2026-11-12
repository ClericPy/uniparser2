# uniparser2 parsing-chain report

What each case ran on, what its selector matched, and what came out: every entry below is the result of a **real run** (`uv run python tools/demo_report.py --md`). This file is generated — regenerate it after changing an operator; `tests/report/test_catalogue.py` fails when it is stale (`UP2_UPDATE_REPORT=1 uv run pytest tests/report` rewrites it). The local HTML build (`.cache/report/up2-report.html`) shows installed/missing dependency state and is not committed.

Generated from `uniparser2` 0.7.0 · one case per `(operator, action)` pair the catalogue covers (the coverage check above names any pair it does not), plus multi-stage compositions, the shared mechanisms and the compile-time invalid forms.

## Coverage check

- **Coverage gap**: missing [('node', 'call'), ('type', 'check')] · non-Ok behavior cases []
- the registry declares **81** pairs = **80** pairs covered by cases
- states across every run: `Failed` 10, `Ok` 113

| operator | arity | slots | summary | actions |
|---|---|---|---|---|
| `css` | 3 | accessor / selector | CSS selector (all matches) | 8 |
| `css1` | 3 | accessor / selector | CSS selector (first match only) | 8 |
| `py` | 3 | function / params | Python built-in allowlist functions | 48 |
| `xpath` | 3 | accessor / XPath | XPath query (XML; lxml) | 3 |
| `json` | 2 | jmespath path | JSON dot-path query (jmespath) | 1 |
| `re` | 3 | mode / pattern | Regex matching (search / findall / sub) | 3 |
| `ctx` | 3 | action / parameter | Scope reads and writes (get / set / del / dict / list) | 5 |
| `each` | 2 | fields | One dictionary per element of a list | 1 |
| `code` | 2 | source | In-chain code (sandboxed; optional dependency [code]) | 1 |
| `udf` | 3 | action / parameter | Host-registered named function (the chain carries no code) | 1 |


## Commonness tiers

Commonness is a **design judgement**, not telemetry: the tiers follow the "standard action chain for field extraction", and the table lives in `tools/demo_report.py`.

| mark | tier | meaning |
|---|---|---|
| ★★★ | Core | almost always used for field extraction |
| ★★ | Common | a regular for cleaning / extraction / URL building |
| ★ | Advanced | list handling, encodings, specific formats |
| ○ | Rare | fallbacks or rarely used |


## `css` — CSS selector (all matches)

arity 3 · slot 2=accessor / slot 3=selector · dependencies: `selectolax` · 8 actions (Core, Common, Advanced)

Input sample for this section — the same input for every card below:

```text
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
```

### Actions (sorted by commonness)

#### `text` — plain text
- tier ★★★ Core · parameter slot: the value itself · `selector: literal`
- note: plain text (no script/style/noscript)
- matched: `1 node · h1.article-title`
- chain: `[["css", "text", "h1.article-title"]]`
- input: the section sample above (shown in full)
- output: `Ok(value=['  Notice on Issuing the Government Service Item List  '])` (Ok)

#### `@<attribute>` — attribute value
- tier ★★★ Core · parameter slot: the value itself · `attr: literal`, `selector: literal`
- note: attribute value; absent ⇒ ""
- matched: `1 node · a.download`
- chain: `[["css", "@href", "a.download"]]`
- input: the section sample above (shown in full)
- output: `Ok(value=['/files/list.pdf'])` (Ok)

#### `html` — inner HTML
- tier ★★ Common · parameter slot: the value itself · `selector: literal`
- note: inner HTML
- matched: `1 node · div.content`
- chain: `[["css", "html", "div.content"]]`
- input: the section sample above (shown in full)
- output: `Ok(value=['\n      <script>console.log(\'this script must not reach the body\');</script>\n      <p>To all municipal governments:</p>\n      <p>The Government Service Item List is …` (Ok)

#### `remove` — a copy with the matching nodes pruned
- tier ★★ Common · parameter slot: the value itself · `selector: literal`
- note: pure function: pruned copy
- matched: `1 node · script`
- chain: `[["css", "remove", "script,style"]]`
- input: the section sample above (shown in full)
- output: `Ok(value=<DomNode HTMLParser>)` (Ok)

#### `nodes` — the set of matching nodes
- tier ★★ Common · parameter slot: the value itself · `selector: literal`
- note: node set for L2 fan-out (not a value)
- matched: `2 nodes · a (×2)`
- chain: `[["css", "nodes", "ul.rel a"]]`
- input: the section sample above (shown in full)
- output: `Ok(value=[<DomNode Node>, <DomNode Node>])` (Ok)

#### `exists` — whether the selector matches at least one node
- tier ★★ Common · parameter slot: the value itself · `selector: literal`
- note: boolean: does the selector match
- matched: `2 nodes · a (×2)`
- chain: `[["css", "exists", "ul.rel a"]]`
- input: the section sample above (shown in full)
- output: `Ok(value=True)` (Ok)

#### `outer` — outer HTML
- tier ★ Advanced · parameter slot: the value itself · `selector: literal`
- note: outer HTML (with its own tag)
- matched: `1 node · h1.article-title`
- chain: `[["css", "outer", "h1.article-title"]]`
- input: the section sample above (shown in full)
- output: `Ok(value=['<h1 class="article-title">  Notice on Issuing the Government Service Item List  </h1>'])` (Ok)

#### `self` — the node handle itself
- tier ★ Advanced · parameter slot: the value itself · `selector: literal`
- note: handle of the first match
- matched: `1 node · div.content`
- chain: `[["css", "self", "div.content"]]`
- input: the section sample above (shown in full)
- output: `Ok(value=<DomNode Node>)` (Ok)

### Compositions (multi-stage chains)

#### `composition` — css
- tier ★★★ Core
- note: prune → take HTML → convert to Markdown (the standard body-extraction trio)
- chain:
  - `["css", "remove", "script,style"]` → `Ok(value='<opaque DomNode>')`
  - `["css1", "html", "div.content"]` → `Ok(value='"\\n      \\n      <p>To all municipal governments:</p>\\n      <p>The Government Service Item List is hereby issued to you; please comply.</p>\\n      <a class=\\"download\\" hre…)`
  - `["py", "html_to_markdown"]` → `Ok(value='To all municipal governments:\n\nThe Government Service Item List is hereby issued to you; please comply.\n\n[Download the list](/files/list.pdf)\n')`
- input: the section sample above (shown in full)
- output: `Ok(value='To all municipal governments:\n\nThe Government Service Item List is hereby issued to you; please comply.\n\n[Download the list](/files/list.pdf)\n')` (Ok)

#### `composition` — css
- tier ★★★ Core
- note: css yields a list: every href at once
- matched: `2 nodes · a (×2)`
- chain: `[["css", "@href", "ul.rel a"]]`
- input: the section sample above (shown in full)
- output: `Ok(value=['/p/1.html', '/p/2.html'])` (Ok)

#### `composition` — css
- tier ★★★ Core
- note: node set → count
- chain:
  - `["css", "nodes", "ul.rel a"]` → `Ok(value=['<DomNode Node>', '<DomNode Node>'])`
  - `["py", "len"]` → `Ok(value=2)`
- input: the section sample above (shown in full)
- output: `Ok(value=2)` (Ok)

#### `composition` — css
- tier ★★★ Core
- note: node set → one dictionary per list item (each): the per-item shape
- chain:
  - `["css", "nodes", "ul.rel li"]` → `Ok(value='/p/2.html')`
  - `["each", {"title": [["css1", "text", "a"]], "href": [["css1", "@href", "a"]]}]` → `Ok(value=[{'title': 'Related one', 'href': '/p/1.html'}, {'title': 'Related two', 'href': '/p/2.html'}])`
- input: the section sample above (shown in full)
- output: `Ok(value=[{'title': 'Related one', 'href': '/p/1.html'}, {'title': 'Related two', 'href': '/p/2.html'}])` (Ok)

### Invalid forms

| invalid chain | code | pointer | message | fix |
|---|---|---|---|---|
| `[["css", "txt", "h1"]]` | `UP2-E1002` | `/0/1` | operator 'css' does not know action 'txt' | use one of the following legal actions |
| `[["css", "@", "h1"]]` | `UP2-E1002` | `/0/1` | an attribute name must follow `@` | write "@href" / "@content" |
| `[["css", "text", "!!!"]]` | `UP2-E1005` | `/0/2/selector` | invalid CSS selector: Bad CSS Selectors: !!! | fix the selector; an empty string means "the current node itself" |
| `[["css", "$text", "h1"]]` | `UP2-E1002` | `/0/1` | operator 'css' does not know action '$text' | use one of the following legal actions |


## `css1` — CSS selector (first match only)

arity 3 · slot 2=accessor / slot 3=selector · dependencies: `selectolax` · 8 actions (Core, Common, Advanced)

Input sample for this section — the same input for every card below:

```text
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
```

### Actions (sorted by commonness)

#### `text` — plain text
- tier ★★★ Core · parameter slot: the value itself · `selector: literal`
- note: plain text (no script/style/noscript)
- matched: `1 node · h1.article-title`
- chain: `[["css1", "text", "h1.article-title"]]`
- input: the section sample above (shown in full)
- output: `Ok(value='  Notice on Issuing the Government Service Item List  ')` (Ok)

#### `@<attribute>` — attribute value
- tier ★★★ Core · parameter slot: the value itself · `attr: literal`, `selector: literal`
- note: attribute value; absent ⇒ ""
- matched: `1 node · a.download`
- chain: `[["css1", "@href", "a.download"]]`
- input: the section sample above (shown in full)
- output: `Ok(value='/files/list.pdf')` (Ok)

#### `html` — inner HTML
- tier ★★ Common · parameter slot: the value itself · `selector: literal`
- note: inner HTML
- matched: `1 node · div.content`
- chain: `[["css1", "html", "div.content"]]`
- input: the section sample above (shown in full)
- output: `Ok(value='\n      <script>console.log(\'this script must not reach the body\');</script>\n      <p>To all municipal governments:</p>\n      <p>The Government Service Item List is h…` (Ok)

#### `remove` — a copy with the matching nodes pruned
- tier ★★ Common · parameter slot: the value itself · `selector: literal`
- note: pure function: pruned copy
- matched: `1 node · script`
- chain: `[["css1", "remove", "script,style"]]`
- input: the section sample above (shown in full)
- output: `Ok(value=<DomNode HTMLParser>)` (Ok)

#### `nodes` — the set of matching nodes
- tier ★★ Common · parameter slot: the value itself · `selector: literal`
- note: node set for L2 fan-out (not a value)
- matched: `2 nodes · a (×2) — only the first match is used`
- chain: `[["css1", "nodes", "ul.rel a"]]`
- input: the section sample above (shown in full)
- output: `Ok(value=[<DomNode Node>])` (Ok)

#### `exists` — whether the selector matches at least one node
- tier ★★ Common · parameter slot: the value itself · `selector: literal`
- note: boolean: does the selector match
- matched: `2 nodes · a (×2) — only the first match is used`
- chain: `[["css1", "exists", "ul.rel a"]]`
- input: the section sample above (shown in full)
- output: `Ok(value=True)` (Ok)

#### `outer` — outer HTML
- tier ★ Advanced · parameter slot: the value itself · `selector: literal`
- note: outer HTML (with its own tag)
- matched: `1 node · h1.article-title`
- chain: `[["css1", "outer", "h1.article-title"]]`
- input: the section sample above (shown in full)
- output: `Ok(value='<h1 class="article-title">  Notice on Issuing the Government Service Item List  </h1>')` (Ok)

#### `self` — the node handle itself
- tier ★ Advanced · parameter slot: the value itself · `selector: literal`
- note: handle of the first match
- matched: `1 node · div.content`
- chain: `[["css1", "self", "div.content"]]`
- input: the section sample above (shown in full)
- output: `Ok(value=<DomNode Node>)` (Ok)

### Compositions (multi-stage chains)

#### `composition` — css1
- tier ★★★ Core
- note: take the heading → normalize whitespace
- chain:
  - `["css1", "text", "h1.article-title"]` → `Ok(value='  Notice on Issuing the Government Service Item List  ')`
  - `["py", "normalize_space"]` → `Ok(value='Notice on Issuing the Government Service Item List')`
- input: the section sample above (shown in full)
- output: `Ok(value='Notice on Issuing the Government Service Item List')` (Ok)

#### `composition` — css1
- tier ★★★ Core
- note: take the attribute → build the absolute URL
- chain:
  - `["css1", "@href", "a.download"]` → `Ok(value='/files/list.pdf')`
  - `["py", "urljoin", "https://x/p/"]` → `Ok(value='https://x/files/list.pdf')`
- input: the section sample above (shown in full)
- output: `Ok(value='https://x/files/list.pdf')` (Ok)

#### `composition` — css
- tier ★★★ Core
- note: extract → process in the sandbox (allowlisted functions need no import)
- chain:
  - `["css1", "text", "h1.article-title"]` → `Ok(value='  Notice on Issuing the Government Service Item List  ')`
  - `["code", "normalize_space(obj)"]` → `Ok(value='Notice on Issuing the Government Service Item List')`
- input: the section sample above (shown in full)
- output: `Ok(value='Notice on Issuing the Government Service Item List')` (Ok)


## `py` — Python built-in allowlist functions

arity 3 · slot 2=function / slot 3=params · dependencies: none · 48 actions (Core, Common, Advanced, Rare)

### Actions (sorted by commonness)

#### `const` — produce the literal value verbatim (never resolved as a reference)
- tier ★★★ Core · parameter slot: the value itself · `value: literal`
- note: a literal written in the chain; the upstream is never read
- chain: `[["py", "const", "article"]]`
- input: not used — the value comes from the chain, never from the upstream
- output: `Ok(value='article')` (Ok)

#### `strip` — strip leading and trailing whitespace, or the given characters
- tier ★★★ Core · parameter slot: the value itself · `chars: literal?, default None`
- note: strip leading/trailing whitespace
- chain: `[["py", "strip"]]`
- input: `  text  `
- output: `Ok(value='text')` (Ok)

#### `normalize_space` — collapse runs of whitespace into a single space
- tier ★★★ Core · parameter slot: no parameter (write two positions, or "")
- note: collapse consecutive whitespace
- chain: `[["py", "normalize_space"]]`
- input:

  ```text
  a   b
   c
  ```
- output: `Ok(value='a b c')` (Ok)

#### `urljoin` — resolve relative to absolute
- tier ★★★ Core · parameter slot: the value itself · `base: ref_or_literal`
- note: relative to absolute (pass base)
- chain: `[["py", "urljoin", "https://x/p/"]]`
- input: `a.html`
- output: `Ok(value='https://x/p/a.html')` (Ok)

#### `first` — take the first element
- tier ★★★ Core · parameter slot: no parameter (write two positions, or "")
- note: first item (xpath/css yield a list; a scalar is needed)
- chain: `[["py", "first"]]`
- input: `['a', 'b']`
- output: `Ok(value='a')` (Ok)

#### `getitem` — take a subscript: a sequence index, a mapping key or a str character
- tier ★★★ Core · parameter slot: the value itself · `at: ref_or_literal`
- note: dict key lookup (a missing key ⇒ UP2-E2018)
- chain: `[["py", "getitem", "k"]]`
- input: `{'k': 7}`
- output: `Ok(value=7)` (Ok)

#### `getattr` — read an attribute of the value that flows in (a host object's own attribute)
- tier ★★★ Core · parameter slot: the value itself · `ref_or_literal: ref_or_literal`
- note: read an attribute of a host object (never a callable one)
- chain: `[["py", "getattr", "status"]]`
- input: `_HostObject(status=200, url='https://example.com/list.html')`
- output: `Ok(value=200)` (Ok)

#### `len` — length
- tier ★★★ Core · parameter slot: no parameter (write two positions, or "")
- note: length
- chain: `[["py", "len"]]`
- input: `[1, 2, 3]`
- output: `Ok(value=3)` (Ok)

#### `slice` — slice a string or list
- tier ★★★ Core · parameter slot: the value itself · `spec: literal`
- note: slice: ":3" / "1:5" / "::-1"
- chain: `[["py", "slice", ":3"]]`
- input: `abcdef`
- output: `Ok(value='abc')` (Ok)

#### `getitem` — take a subscript: a sequence index, a mapping key or a str character
- tier ★★ Common · parameter slot: the value itself · `at: ref_or_literal`
- note: list index (out of range ⇒ UP2-E2018)
- chain: `[["py", "getitem", 1]]`
- input: `['a', 'b']`
- output: `Ok(value='b')` (Ok)

#### `last` — take the last element
- tier ★★ Common · parameter slot: no parameter (write two positions, or "")
- note: last item
- chain: `[["py", "last"]]`
- input: `[1, 2]`
- output: `Ok(value=2)` (Ok)

#### `replace` — replace all occurrences
- tier ★★ Common · parameter slot: array · `old: literal`, `new: literal`
- note: replace all (positional array)
- chain: `[["py", "replace", ["old", "new"]]]`
- input: `old document`
- output: `Ok(value='new document')` (Ok)

#### `split` — split on a separator
- tier ★★ Common · parameter slot: the value itself · `sep: literal`
- note: split on a separator
- chain: `[["py", "split", ","]]`
- input: `a,b,c`
- output: `Ok(value=['a', 'b', 'c'])` (Ok)

#### `join` — join a list
- tier ★★ Common · parameter slot: the value itself · `sep: literal`
- note: join a list
- chain: `[["py", "join", "-"]]`
- input: `['a', 'b']`
- output: `Ok(value='a-b')` (Ok)

#### `find_jsons` — every JSON object/array embedded in the text, parsed, in document order
- tier ★★ Common · parameter slot: no parameter (write two positions, or "")
- note: every embedded JSON value
- chain: `[["py", "find_jsons"]]`
- input: `x{"a": 1}y`
- output: `Ok(value=[{'a': 1}])` (Ok)

#### `md5` — hexadecimal digest (checksums only, not security)
- tier ★★ Common · parameter slot: no parameter (write two positions, or "")
- note: checksum (not for security)
- chain: `[["py", "md5"]]`
- input: `abc`
- output: `Ok(value='900150983cd24fb0d6963f7d28e17f72')` (Ok)

#### `between` — lo <= value < hi (numbers only, half-open)
- tier ★★ Common · parameter slot: the value itself · `bounds: ref_or_literal`
- note: half-open numeric interval
- chain: `[["py", "between", [200, 300]]]`
- input: `250`
- output: `Ok(value=True)` (Ok)

#### `html_to_markdown` — HTML -> Markdown (no parameters; complete relative links with py.urljoin)
- tier ★★ Common · parameter slot: no parameter (write two positions, or "")
- note: optional dependency [md]
- chain: `[["py", "html_to_markdown"]]`
- input: `<h1>Heading</h1><p>a <b>b</b></p>`
- output: `Ok(value='# Heading\n\na **b**\n')` (Ok)

#### `int` — convert to an integer (former cast int)
- tier ★★ Common · parameter slot: no parameter (write two positions, or "")
- note: type conversion (formerly cast int)
- chain: `[["py", "int"]]`
- input: `42`
- output: `Ok(value=42)` (Ok)

#### `str` — convert to a string (former cast str)
- tier ★★ Common · parameter slot: no parameter (write two positions, or "")
- note: type conversion (formerly cast str)
- chain: `[["py", "str"]]`
- input: `42`
- output: `Ok(value='42')` (Ok)

#### `==` — equal to the parameter (no type coercion)
- tier ★★ Common · parameter slot: the value itself · `to: ref_or_literal`
- note: equality with the parameter (no type coercion)
- chain: `[["py", "==", 200]]`
- input: `200`
- output: `Ok(value=True)` (Ok)

#### `!=` — not equal to the parameter
- tier ★★ Common · parameter slot: the value itself · `to: ref_or_literal`
- note: inequality (also negates a boolean: ['!=', true])
- chain: `[["py", "!=", 200]]`
- input: `200`
- output: `Ok(value=True)` (Ok)

#### `in` — is the value in the parameter (Python's in: the parameter is the container)
- tier ★★ Common · parameter slot: the value itself · `container: ref_or_literal`
- note: Python's in: the parameter is the container
- chain: `[["py", "in", [200, 301, 302]]]`
- input: `301`
- output: `Ok(value=True)` (Ok)

#### `or` — the first truthy of [value, *operands], else the last (Python's or)
- tier ★★ Common · parameter slot: the value itself · `operands: ref_or_literal`
- note: Python's or: first truthy, else the last
- chain: `[["py", "or", ["", "fallback"]]]`
- input: `in`
- output: `Ok(value='in')` (Ok)

#### `and` — the first falsy of [value, *operands], else the last (Python's and)
- tier ★★ Common · parameter slot: the value itself · `operands: ref_or_literal`
- note: Python's and: first falsy, else the last
- chain: `[["py", "and", [{"a": 1}, ""]]]`
- input: `in`
- output: `Ok(value='')` (Ok)

#### `strptime` — parse text with an explicit format into a datetime
- tier ★★ Common · parameter slot: the value itself · `format: literal`
- note: text → datetime, rendered back to text
- chain:
  - `["py", "strptime", "%Y-%m-%d %H:%M:%S"]` → `Ok(value='datetime datetime.datetime(2026, 9, 24, 15, 30)')`
  - `["py", "strftime", "%Y-%m-%d"]` → `Ok(value='2026-09-24')`
- input: `2026-09-24 15:30:00`
- output: `Ok(value='2026-09-24')` (Ok)

#### `filter` — keep truthy elements (or falsy ones when keep is false)
- tier ★★ Common · parameter slot: the value itself · `keep: literal?, default True`
- note: keep truthy elements
- chain: `[["py", "filter"]]`
- input: `[0, 1, '', 'a', None]`
- output: `Ok(value=[1, 'a'])` (Ok)

#### `strftime` — render a datetime with a layout
- tier ★★ Common · parameter slot: the value itself · `layout: literal`
- note: a datetime → text
- chain:
  - `["py", "strptime", "%Y-%m-%d %H:%M:%S"]` → `Ok(value='datetime datetime.datetime(2026, 9, 24, 15, 30)')`
  - `["py", "strftime", "%Y-%m-%d"]` → `Ok(value='2026-09-24')`
- input: `2026-09-24 15:30:00`
- output: `Ok(value='2026-09-24')` (Ok)

#### `upper` — convert to uppercase
- tier ★ Advanced · parameter slot: no parameter (write two positions, or "")
- note: uppercase
- chain: `[["py", "upper"]]`
- input: `abc`
- output: `Ok(value='ABC')` (Ok)

#### `lower` — convert to lowercase
- tier ★ Advanced · parameter slot: no parameter (write two positions, or "")
- note: lowercase
- chain: `[["py", "lower"]]`
- input: `ABC`
- output: `Ok(value='abc')` (Ok)

#### `flatten` — flatten one level
- tier ★ Advanced · parameter slot: no parameter (write two positions, or "")
- note: flatten one level
- chain: `[["py", "flatten"]]`
- input: `[[1, 2], [3]]`
- output: `Ok(value=[1, 2, 3])` (Ok)

#### `sort` — Python's sorted
- tier ★ Advanced · parameter slot: no parameter (write two positions, or "")
- note: stable sort
- chain: `[["py", "sort"]]`
- input: `[3, 1, 2]`
- output: `Ok(value=[1, 2, 3])` (Ok)

#### `uniq` — deduplicate while preserving order
- tier ★ Advanced · parameter slot: no parameter (write two positions, or "")
- note: deduplicate, keeping order
- chain: `[["py", "uniq"]]`
- input: `[1, 1, 2]`
- output: `Ok(value=[1, 2])` (Ok)

#### `urlsplit` — split a URL into parts
- tier ★ Advanced · parameter slot: the value itself · `part: literal`
- note: URL parts (take the site identity)
- chain: `[["py", "urlsplit", "netloc"]]`
- input: `https://x/a?q=1`
- output: `Ok(value='x')` (Ok)

#### `b64_decode` — Base64 decode
- tier ★ Advanced · parameter slot: no parameter (write two positions, or "")
- note: Base64 decode
- chain: `[["py", "b64_decode"]]`
- input: `YWJj`
- output: `Ok(value='abc')` (Ok)

#### `sha256` — hexadecimal digest
- tier ★ Advanced · parameter slot: no parameter (write two positions, or "")
- note: hex digest (idempotency key)
- chain: `[["py", "sha256"]]`
- input: `abc`
- output: `Ok(value='ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')` (Ok)

#### `from_json` — JSON text -> JSON tree (former cast json)
- tier ★ Advanced · parameter slot: no parameter (write two positions, or "")
- note: JSON text → JSON tree (formerly cast json)
- chain: `[["py", "from_json"]]`
- input: `{"a": 1}`
- output: `Ok(value={'a': 1})` (Ok)

#### `float` — convert to a float (former cast float)
- tier ★ Advanced · parameter slot: no parameter (write two positions, or "")
- note: type conversion
- chain: `[["py", "float"]]`
- input: `1.5`
- output: `Ok(value=1.5)` (Ok)

#### `bool` — convert with Python's bool (former cast bool)
- tier ★ Advanced · parameter slot: no parameter (write two positions, or "")
- note: type conversion (falsey word list)
- chain: `[["py", "bool"]]`
- input: `no`
- output: `Ok(value=True)` (Ok)

#### `<` — less than the parameter (two numbers or two strings)
- tier ★ Advanced · parameter slot: the value itself · `to: ref_or_literal`
- note: ordering: two numbers or two strings only
- chain: `[["py", "<", 10]]`
- input: `5`
- output: `Ok(value=True)` (Ok)

#### `<=` — less than or equal to the parameter
- tier ★ Advanced · parameter slot: the value itself · `to: ref_or_literal`
- note: ordering (inclusive)
- chain: `[["py", "<=", 5]]`
- input: `5`
- output: `Ok(value=True)` (Ok)

#### `>` — greater than the parameter
- tier ★ Advanced · parameter slot: the value itself · `to: ref_or_literal`
- note: ordering
- chain: `[["py", ">", 5]]`
- input: `6`
- output: `Ok(value=True)` (Ok)

#### `>=` — greater than or equal to the parameter
- tier ★ Advanced · parameter slot: the value itself · `to: ref_or_literal`
- note: ordering (inclusive)
- chain: `[["py", ">=", "b"]]`
- input: `c`
- output: `Ok(value=True)` (Ok)

#### `items` — a dict becomes [[key, value], ...] (index a pair with the literal 0 / 1)
- tier ★ Advanced · parameter slot: no parameter (write two positions, or "")
- note: dict → key/value pairs (index with the literal 0 / 1)
- chain: `[["py", "items"]]`
- input: `{'a': 1, 'b': 2}`
- output: `Ok(value=[['a', 1], ['b', 2]])` (Ok)

#### `sort_desc` — Python's sorted(reverse=True)
- tier ★ Advanced · parameter slot: no parameter (write two positions, or "")
- note: stable descending sort
- chain: `[["py", "sort_desc"]]`
- input: `[2, 3, 1]`
- output: `Ok(value=[3, 2, 1])` (Ok)

#### `from_timestamp` — epoch seconds -> an aware datetime at a fixed offset
- tier ★ Advanced · parameter slot: the value itself · `tz: ref_or_literal?, default None`
- note: epoch seconds → aware datetime → text
- chain:
  - `["py", "from_timestamp", 8]` → `Ok(value='datetime datetime.datetime(1970, 1, 1, 8, 0, tzinfo=datetime.timezone(datetime.timedelta(seconds=28800)))')`
  - `["py", "strftime", "%Y-%m-%d %H:%M:%S"]` → `Ok(value='1970-01-01 08:00:00')`
- input: `0`
- output: `Ok(value='1970-01-01 08:00:00')` (Ok)

#### `to_timestamp` — a datetime -> epoch seconds (a naive value is read at tz, UTC by default)
- tier ★ Advanced · parameter slot: the value itself · `tz: ref_or_literal?, default None`
- note: a datetime → epoch seconds
- chain:
  - `["py", "strptime", "%Y-%m-%d"]` → `Ok(value='datetime datetime.datetime(2026, 9, 24, 0, 0)')`
  - `["py", "to_timestamp"]` → `Ok(value=1790208000)`
- input: `2026-09-24`
- output: `Ok(value=1790208000)` (Ok)

#### `b64_encode` — Base64 encode
- tier ○ Rare · parameter slot: no parameter (write two positions, or "")
- note: Base64 encode
- chain: `[["py", "b64_encode"]]`
- input: `abc`
- output: `Ok(value='YWJj')` (Ok)

#### `sleep` — block for the given seconds and return the upstream value
- tier ○ Rare · parameter slot: the value itself · `seconds: ref_or_literal`
- note: block for the given seconds, return the upstream
- chain: `[["py", "sleep", 0]]`
- input: `kept`
- output: `Ok(value='kept')` (Ok)

### Compositions (multi-stage chains)

#### `composition` — py
- tier ★★★ Core
- note: normalize to the canonical time → render another layout (the output side)
- chain:
  - `["py", "strptime", "%Y-%m-%d %H:%M:%S"]` → `Ok(value='datetime datetime.datetime(2026, 9, 24, 15, 30)')`
  - `["py", "strftime", "%Y/%m/%d"]` → `Ok(value='2026/09/24')`
- input: `2026-09-24 15:30:00`
- output: `Ok(value='2026/09/24')` (Ok)

#### `composition` — py
- tier ★★★ Core
- note: parse the JSON text first, then use the json operator to take a subtree
- chain:
  - `["py", "from_json"]` → `Ok(value={'data': {'html': '<p>Body</p>', 'list': [{'url': 'u1'}, {'url': 'u2'}]}})`
  - `["json", "data.html"]` → `Ok(value='<p>Body</p>')`
- input: `{"data": {"html": "<p>Body</p>", "list": [{"url": "u1"}, {"url": "u2"}]}}`
- output: `Ok(value='<p>Body</p>')` (Ok)

#### `composition` — py
- tier ★★★ Core
- note: a parameter referencing globals
- scope: `globals {'base': 'https://example.gov.cn/p/'}`
- chain: `[["py", "urljoin", "$globals.base"]]`
- input: `a.html`
- output: `Ok(value='https://example.gov.cn/p/a.html')` (Ok)

#### `composition` — py
- tier ★★★ Core
- note: convert → regex → convert again
- chain:
  - `["py", "str"]` → `Ok(value='2026')`
  - `["re", "search", "\\d+"]` → `Ok(value='2026')`
  - `["py", "int"]` → `Ok(value=2026)`
- input: `2026`
- output: `Ok(value=2026)` (Ok)

#### `composition` — py
- tier ★★★ Core
- note: time normalization → take the date part
- chain:
  - `["py", "strptime", "%Y/%m/%d %H:%M:%S"]` → `Ok(value='datetime datetime.datetime(2026, 9, 24, 15, 30)')`
  - `["py", "strftime", "%Y-%m-%d"]` → `Ok(value='2026-09-24')`
- input: `2026/09/24 15:30:00`
- output: `Ok(value='2026-09-24')` (Ok)

### Invalid forms

| invalid chain | code | pointer | message | fix |
|---|---|---|---|---|
| `[["py"]]` | `UP2-E1004` | `/0` | py needs 3 slots, got 1 | this operator's slots are slot2=function, slot3=params; drop the parameter slot when the action declares nothing required |
| `[["py", "strip", "", ""]]` | `UP2-E1004` | `/0` | stage length is 4, only 1 to 3 is allowed | follow the declared arity: 3 slots is ["operator", action, parameter]; 2 slots is ["operator", parameter] or ["operator", action]; 1 slot is a single-action operator whose parameter is omitted |
| `[["py", "no_such_function", ""]]` | `UP2-E1003` | `/0/1` | the py allowlist has no function 'no_such_function' | use one of the functions below (run up2 ops --json for the full table) |
| `[["py", "strptime", "%Q"]]` | `UP2-E1005` | `/0/2/format` | unknown directive %Q in strptime's format | use numeric directives such as "%Y-%m-%d" / "%H:%M:%S", or reshape the pieces with py.slice |
| `[["py", "urljoin", "$nope.x"]]` | `UP2-E1006` | `/0/2` | unknown reference root 'nope' | use a reserved root, or declare an external product root with --product; for text that starts with `$`, write {"$lit": "…"} |
| `[["py", "urljoin", {"base": "https://example.com/news/"}]]` | `UP2-E1005` | `/0/2/base` | parameter 'base' of py.urljoin must be a string, got dict | write the value directly: ["py", "urljoin", "…"] |
| `[["py", "slice", {"spec": "0:4"}]]` | `UP2-E1005` | `/0/2/spec` | parameter 'spec' of py.slice must be a string, got dict | write the value directly: ["py", "slice", "…"] |
| `[["py", "getitem", {"at": {}}]]` | `UP2-E1005` | `/0/2/at` | parameter 'at' of py.getitem must be a scalar, got dict | write the value directly: ["py", "getitem", "…"] |
| `[["py", "split", {"sep": {}}]]` | `UP2-E1005` | `/0/2/sep` | parameter 'sep' of py.split must be a string, got dict | write the value directly: ["py", "split", "…"] |
| `[["py", "sort", "int"]]` | `UP2-E1004` | `/0/2` | action 'sort' takes no parameter, but 'int' was written in the slot | drop the slot: the action has nothing left to configure |


## `xpath` — XPath query (XML; lxml)

arity 3 · slot 2=accessor / slot 3=XPath · dependencies: `lxml` · 3 actions (Core, Common, Advanced)

Input sample for this section — the same input for every card below:

```text
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://x/1</loc><lastmod>2026-09-23</lastmod></url>
  <url><loc>https://x/2</loc><lastmod>2026-09-24</lastmod></url>
</urlset>
```

### Actions (sorted by commonness)

#### `text` — text value (elements: all descendant text; attributes as-is)
- tier ★★★ Core · parameter slot: array · `expr: literal`, `ns: literal?, default None`
- matched: `2 nodes · loc (×2)`
- chain: `[["xpath", "text", "//*[local-name()='loc']"]]`
- input: the section sample above (shown in full)
- output: `Ok(value=['https://x/1', 'https://x/2'])` (Ok)

#### `nodes` — the set of matching nodes
- tier ★★ Common · parameter slot: array · `expr: literal`, `ns: literal?, default None`
- matched: `2 nodes · url (×2)`
- chain: `[["xpath", "nodes", "//*[local-name()='url']"]]`
- input: the section sample above (shown in full)
- output: `Ok(value=[<XPathNode {http://www.sitemaps.org/schemas/sitemap/0.9}url>, <XPathNode {http://www.sitemaps.org/schemas/sitemap/0.9}url>])` (Ok)

#### `self` — the first matching node (relative paths can keep selecting)
- tier ★ Advanced · parameter slot: array · `expr: literal`, `ns: literal?, default None`
- matched: `2 nodes · url (×2)`
- chain: `[["xpath", "self", "//*[local-name()='url']"]]`
- input: the section sample above (shown in full)
- output: `Ok(value=<XPathNode {http://www.sitemaps.org/schemas/sitemap/0.9}url>)` (Ok)

### Compositions (multi-stage chains)

#### `composition` — xpath
- tier ★★★ Core
- note: sitemap: every lastmod → take the last
- chain:
  - `["xpath", "text", "//*[local-name()='lastmod']"]` → `Ok(value=['2026-09-23', '2026-09-24'])`
  - `["py", "last"]` → `Ok(value='2026-09-24')`
- input: the section sample above (shown in full)
- output: `Ok(value='2026-09-24')` (Ok)

#### `composition` — xpath
- tier ★★★ Core
- note: namespace prefix: slot 3 takes an object form carrying the ns map
- matched: `1 node · creator`
- chain: `[["xpath", "text", ["//dc:creator", {"dc": "http://purl.org/dc/elements/1.1/"}]]]`
- input:

  ```text
  <?xml version="1.0" encoding="UTF-8"?>
  <rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/">
    <channel><item><title>Headline</title><dc:creator>Jane Reporter</dc:creator></item></channel>
  </rss>
  ```
- output: `Ok(value=['Jane Reporter'])` (Ok)

### Invalid forms

| invalid chain | code | pointer | message | fix |
|---|---|---|---|---|
| `[["xpath", "text", "//dc:creator"]]` | `UP2-E1005` | `/0/2/expr` | the XPath expression is unusable: Undefined namespace prefix | fix expr; provide an ns mapping, e.g. {"dc": "http://purl.org/dc/elements/1.1/"} |


## `json` — JSON dot-path query (jmespath)

arity 2 · slot 2=jmespath path · dependencies: `jmespath` · 1 actions (Core)

### Actions (sorted by commonness)

#### `get` — jmespath query (empty expression = the root)
- tier ★★★ Core · parameter slot: the value itself · `expr: literal?, default ''`
- note: 2 positions: action slot omitted
- chain: `[["json", "data.list[*].url"]]`
- input: `{"data": {"html": "<p>Body</p>", "list": [{"url": "u1"}, {"url": "u2"}]}}`
- output: `Ok(value=['u1', 'u2'])` (Ok)

### Compositions (multi-stage chains)

#### `composition` — json
- tier ★★★ Core
- note: take all URLs → take the first
- chain:
  - `["json", "data.list[*].url"]` → `Ok(value=['u1', 'u2'])`
  - `["py", "first"]` → `Ok(value='u1')`
- input: `{"data": {"html": "<p>Body</p>", "list": [{"url": "u1"}, {"url": "u2"}]}}`
- output: `Ok(value='u1')` (Ok)

### Invalid forms

| invalid chain | code | pointer | message | fix |
|---|---|---|---|---|
| `[["json", "("]]` | `UP2-E1005` | `/0/1/expr` | invalid jmespath expression: Invalid jmespath expression: Incomplete expression:<br>"("<br>  ^ | fix the path (e.g. data.list[*].url, data.html, or an empty string for the root) |


## `re` — Regex matching (search / findall / sub)

arity 3 · slot 2=mode / slot 3=pattern · dependencies: none · 3 actions (Core, Common, Advanced)

### Actions (sorted by commonness)

#### `search` — the first match, or one of its capture groups
- tier ★★★ Core · parameter slot: array · `pattern: literal`, `group: literal?, default None`
- chain: `[["re", "search", "\\d{4}-\\d{2}-\\d{2}"]]`
- input: `published 2026-09-24 end`
- output: `Ok(value='2026-09-24')` (Ok)

#### `group` — re
- tier ★★ Common
- note: named object: pattern + group
- chain: `[["re", "search", ["(\\d{4})-(\\d{2})", 2]]]`
- input: `2026-09`
- output: `Ok(value='09')` (Ok)

#### `findall` — findall: every match
- tier ★ Advanced · parameter slot: the value itself · `pattern: literal`
- chain: `[["re", "findall", "\\d+"]]`
- input: `a1b22c333`
- output: `Ok(value=['1', '22', '333'])` (Ok)

#### `sub` — replace every match (Python's \N / \g<name> in the replacement)
- tier ★ Advanced · parameter slot: array · `pattern: literal`, `replacement: literal`
- note: replace every match
- chain: `[["re", "sub", ["\\d+", "#"]]]`
- input: `a1b22`
- output: `Ok(value='a#b#')` (Ok)

### Compositions (multi-stage chains)

#### `composition` — re
- tier ★★★ Core
- note: whole text → the year inside it
- chain:
  - `["re", "search", "\\d{4}-\\d{2}-\\d{2}"]` → `Ok(value='2026-09-24')`
  - `["re", "search", "\\d{4}"]` → `Ok(value='2026')`
- input: `published 2026-09-24 end`
- output: `Ok(value='2026')` (Ok)

### Invalid forms

| invalid chain | code | pointer | message | fix |
|---|---|---|---|---|
| `[["re", "search", ["a", 9]]]` | `UP2-E1005` | `/0/2/group` | the pattern has only 0 capture groups, so group 9 is unavailable | change the group index, or add a capture group to the pattern |


## `ctx` — Scope reads and writes (get / set / del / dict / list)

arity 3 · slot 2=action / slot 3=parameter · dependencies: none · 5 actions (Common, Advanced, Rare)

### Actions (sorted by commonness)

#### `get` — read a scope path
- tier ★★ Common · parameter slot: the value itself · `path: literal`
- scope: `locals {'k': 'local value'}`
- chain: `[["ctx", "get", "locals.k"]]`
- input: not used — the value is read from the scope path
- output: `Ok(value='local value')` (Ok)

#### `set` — write the upstream value into locals or public
- tier ★★ Common · parameter slot: the value itself · `path: literal`
- note: the write surface is limited to locals
- chain: `[["ctx", "set", "locals.k"]]`
- input: `written value`
- output: `Ok(value='written value')` (Ok)

#### `dict` — collect several paths into an object (name → path)
- tier ★ Advanced · parameter slot: the value itself · `refs: literal`
- note: name → path object → dict
- scope: `locals {'x': 1, 'y': 2}`
- chain: `[["ctx", "dict", {"a": "locals.x", "b": "locals.y"}]]`
- input: not used — the values are read from the scope paths
- output: `Ok(value={'a': 1, 'b': 2})` (Ok)

#### `list` — collect several paths into a list (an array of paths)
- tier ★ Advanced · parameter slot: the value itself · `refs: literal`
- note: array of paths → list (feeds a positional call)
- scope: `locals {'x': 1, 'y': 2}`
- chain: `[["ctx", "list", ["locals.x", "locals.y"]]]`
- input: not used — the values are read from the scope paths
- output: `Ok(value=[1, 2])` (Ok)

#### `del` — delete a path in locals or public
- tier ○ Rare · parameter slot: the value itself · `path: literal`
- scope: `locals {'k': 1}`
- chain: `[["ctx", "del", "locals.k"]]`
- input: `upstream value`
- output: `Ok(value='upstream value')` (Ok)

### Compositions (multi-stage chains)

#### `composition` — ctx
- tier ★★★ Core
- note: write to locals → read back (the `_` prefix = internal path)
- chain:
  - `["ctx", "set", "locals._tmp"]` → `Ok(value='intermediate value')`
  - `["ctx", "get", "locals._tmp"]` → `Ok(value='intermediate value')`
- input: `intermediate value`
- output: `Ok(value='intermediate value')` (Ok)

### Invalid forms

| invalid chain | code | pointer | message | fix |
|---|---|---|---|---|
| `[["ctx", "set", "globals.x"]]` | `UP2-E1015` | `/0/2/path` | ctx.set cannot write 'globals.x' | the write surface is limited to locals.* and public.* (globals and product values are read-only) |


## `each` — One dictionary per element of a list

arity 2 · slot 2=fields · dependencies: none · 1 actions (Core)

### Actions (sorted by commonness)

#### `each` — Run the field map once per element
- tier ★★★ Core · parameter slot: the value itself · `fields: fields_or_chain`
- note: 2 positions: field map; one dictionary per element
- chain: `[["each", {"title": [["py", "strip"]], "size": [["py", "len"]]}]]`
- input: `['  a  ', 'bb']`
- output: `Ok(value=[{'title': 'a', 'size': 5}, {'title': 'bb', 'size': 2}])` (Ok)


## `code` — In-chain code (sandboxed; optional dependency [code])

arity 2 · slot 2=source · dependencies: `pydantic_monty` · 1 actions (Advanced)

Input sample for this section — the same input for every card below:

```text
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
```

### Actions (sorted by commonness)

#### `run` — run src once and take the value of the last expression
- tier ★ Advanced · parameter slot: the value itself · `src: literal`
- note: sandboxed; optional dependency [code]; the last expression value is returned
- scope: `locals {'prefix': 'Title: '}`
- chain: `[["code", "ctx.locals.prefix + normalize_space(obj)"]]`
- input: the section sample above (shown in full)
- output: `Ok(value='Title: <html> <head> <meta name="PubDate" content="2026-09-24 15:30:00"> <title>Notice on Issuing the Government Service Item List</title> </head> <body> <h1 class="artic…` (Ok)


## `udf` — Host-registered named function (the chain carries no code)

arity 3 · slot 2=action / slot 3=parameter · dependencies: none · 1 actions (Common)

### Actions (sorted by commonness)

#### `*` — registered: demo_upper
- tier ★★ Common · parameter slot: the value itself
- note: dynamic action space: slot 2 carries the host-registered function name
- chain: `[["udf", "demo_upper"]]`
- input: `hello`
- output: `Ok(value='HELLO')` (Ok)

### Invalid forms

| invalid chain | code | pointer | message | fix |
|---|---|---|---|---|
| `[["udf", "not_registered"]]` | `unexpected: no error raised` | `` |  |  |


## Appendix: mechanisms shared by all operators

These are **not grouped by operator**: the outcomes, the parameter forms, the scopes and the guard directive belong to every operator, so slicing them per operator would hide the differences.

### A. Outcomes

A query that matches nothing is a **value** — the empty value of its shape (`""` / `[]` / `null`) — and the chain keeps going. A stage that *fails* stops the chain and is reported with the code it reported; there is no third state.

#### `Ok (a hit)` — outcome
- tier ★★★ Core
- matched: `1 node · h1.article-title`
- chain: `[["css1", "text", "h1.article-title"]]`
- input:

  ```text
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
  ```
- output: `Ok(value='  Notice on Issuing the Government Service Item List  ')` (Ok)

#### `Ok (no match: the empty value of the shape)` — outcome
- tier ★★★ Core
- note: a no-match is a value, not a state: the text accessor answers ''
- matched: `0 nodes`
- chain: `[["css1", "text", "div.nope"]]`
- input:

  ```text
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
  ```
- output: `Ok(value='')` (Ok)

#### `Ok (a list accessor: the empty value of the shape)` — outcome
- tier ★★★ Core
- note: a list accessor answers [] when nothing matches
- matched: `0 nodes`
- chain: `[["css", "nodes", "li.nope"]]`
- input:

  ```text
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
  ```
- output: `Ok(value=[])` (Ok)

#### `Failed (input type mismatch)` — outcome
- tier ★★★ Core
- note: UP2-E2002
- chain: `[["py", "upper"]]`
- input: `42`
- output: `Failed(code='UP2-E2002', reason='py.upper needs a str, got int', fix='turn the upstream value into text with py.str / py.getitem first')` (Failed)

#### `Failed (evaluation failed)` — outcome
- tier ★★★ Core
- note: UP2-E2005
- chain: `[["py", "int"]]`
- input: `abc`
- output: `Failed(code='UP2-E2005', reason="py.int conversion failed: invalid literal for int() with base 10: 'abc'", fix='py.int expects an integer, a float, a bool, or a string of digits; c…` (Failed)

#### `Failed (a subscript that is not there)` — outcome
- tier ★★★ Core
- note: UP2-E2018: the dict is there, the key is not — an error, not an empty value
- chain: `[["py", "getitem", "text"]]`
- input: `{'a': 1}`
- output: `Failed(code='UP2-E2018', reason="KeyError: 'text' — the dict has no key 'text'", fix='read a key the mapping has, or make the producing stage write it')` (Failed)

#### `Failed (an attribute that is a method)` — outcome
- tier ★★★ Core
- note: UP2-E2002: py.getattr never calls a method (the fix names an operator or a udf)
- chain: `[["py", "getattr", "json"]]`
- input: `_HostObject(status=200, url='https://example.com/list.html')`
- output: `Failed(code='UP2-E2002', reason="the attribute 'json' of _HostObject is callable, and py.getattr never calls it", fix='a method is not a value: read the text with ["css","text",""]…` (Failed)

#### `Failed (an absent attribute)` — outcome
- tier ★★★ Core
- note: UP2-E2002 whose reason begins with the exception class: AttributeError: ...
- chain: `[["py", "getattr", "txet"]]`
- input: `_HostObject(status=200, url='https://example.com/list.html')`
- output: `Failed(code='UP2-E2002', reason="AttributeError: '_HostObject' object has no attribute 'txet'", fix='check the attribute name against the value, or make the producing stage write i…` (Failed)

#### `Failed (a path that cannot be read)` — outcome
- tier ★★★ Core
- note: UP2-E2001: a reference path that does not exist is a failure, not an empty value
- chain: `[["ctx", "get", "locals.nope"]]`
- input: `None`
- output: `Failed(code='UP2-E2001', reason="locals.nope is missing key 'nope' at locals", fix='read a key the value has, or make the producing stage write it')` (Failed)

#### `Failed (sandbox code raised)` — outcome
- tier ★★★ Core
- note: UP2-E2017 (the sandbox code can catch it with try/except)
- chain: `[["code", "1 / 0"]]`
- input: `None`
- output: `Failed(code='UP2-E2017', reason='the sandboxed code raised an exception: ZeroDivisionError: division by zero', fix='fix src; the snippet can catch it itself with try/except')` (Failed)

#### `Failed (sandbox execution over limit)` — outcome
- tier ★★★ Core
- note: UP2-E2016: limits are configured by the host (a tiny time budget is used here)
- chain: `[["code", "while True:\n    pass"]]`
- input: `None`
- output: `Failed(code='UP2-E2016', reason='sandbox execution exceeded its limits: TimeoutError: feed time limit exceeded: <measured> fix='reduce the data volume or rewrite the algorithm; lim…` (Failed)

### B. Parameter forms

The scalar / positional array / named object / reference / directive forms of the parameter slot.

#### `scalar parameter` — form
- tier ★★★ Core
- chain: `[["py", "urljoin", "https://x/p/"]]`
- input: `a.html`
- output: `Ok(value='https://x/p/a.html')` (Ok)

#### `positional array` — form
- tier ★★★ Core
- chain: `[["py", "replace", ["old", "new"]]]`
- input: `old text`
- output: `Ok(value='new text')` (Ok)

#### `two parameters in one array` — form
- tier ★★★ Core
- chain: `[["re", "search", ["(\\d+)", 1]]]`
- input: `x42`
- output: `Ok(value='42')` (Ok)

#### `reference ($globals / $locals)` — form
- tier ★★★ Core
- scope: `globals {'base': 'https://x/'}`
- chain: `[["py", "urljoin", "$globals.base"]]`
- input: `a`
- output: `Ok(value='https://x/a')` (Ok)

#### `directive object {"$lit": …}: a literal starting with $` — form
- tier ★★★ Core
- note: without $lit it is a reference (E1006, see the invalid-form sections)
- chain: `[["py", "or", [{"$lit": "$locals.title"}]]]`
- input: ``
- output: `Ok(value='$locals.title')` (Ok)

#### `css empty selector = the current node itself` — form
- tier ★★★ Core
- matched: `1 node · html`
- chain: `[["css1", "text", ""]]`
- input: `<p>plain text supplied directly</p>`
- output: `Ok(value='plain text supplied directly')` (Ok)

### C. The scopes and the guard directive

The three scopes read as **constants / shared / private**: `globals` is the chain's read-only constants, `public` is the run's own notes (writable from any node, never fingerprinted), `locals` is one field's scratch space. `try` is **not an operator**: it guards the next stage only, and a guarded stage that succeeds disarms it.

#### `globals: the chain's read-only constants` — scope
- tier ★★★ Core
- note: read-only: a write outside locals/public is UP2-E1015
- scope: `globals {'base': 'https://example.com'}`
- chain: `[["ctx", "get", "globals.base"]]`
- input: `None`
- output: `Ok(value='https://example.com')` (Ok)

#### `locals: one field's scratch space` — scope
- tier ★★★ Core
- note: private to the field that wrote it
- chain:
  - `["py", "const", "42"]` → `Ok(value='42')`
  - `["ctx", "set", "locals._n"]` → `Ok(value='42')`
  - `["ctx", "get", "locals._n"]` → `Ok(value='42')`
- input: `None`
- output: `Ok(value='42')` (Ok)

#### `public: the run's shared notes` — scope
- tier ★★★ Core
- note: writable and readable from any node; never part of the chain data
- chain:
  - `["py", "const", "42"]` → `Ok(value='42')`
  - `["ctx", "set", "public.n"]` → `Ok(value='42')`
  - `["ctx", "get", "public.n"]` → `Ok(value='42')`
- input: `None`
- output: `Ok(value='42')` (Ok)

#### `public may be collected like any scope` — scope
- tier ★★★ Core
- note: ctx.dict / ctx.list read any scope, globals included
- chain:
  - `["py", "const", "42"]` → `Ok(value='42')`
  - `["ctx", "set", "public.n"]` → `Ok(value='42')`
  - `["ctx", "dict", {"n": "public.n"}]` → `Ok(value={'n': '42'})`
- input: `None`
- output: `Ok(value={'n': '42'})` (Ok)

#### `try skip: a guarded failure keeps the value the chain carried` — guard
- tier ★★★ Core
- note: the guard covers the NEXT stage only, and never turns the error into a value
- chain:
  - `["py", "const", "keep"]` → `Ok(value='keep')`
  - `["try", "skip"]` → `(a directive: it does no work)`
  - `["py", "int"]` → `Failed(UP2-E2005: py.int conversion failed: invalid literal for int() with base 10: 'keep')`
- input: `not-a-number`
- output: `Ok(value='keep')` (Ok)

#### `try break: a guarded failure ends the chain with that value` — guard
- tier ★★★ Core
- note: the stages after the guarded one are not evaluated
- chain:
  - `["py", "const", "keep"]` → `Ok(value='keep')`
  - `["try", "break"]` → `(a directive: it does no work)`
  - `["py", "int"]` → `Failed(UP2-E2005: py.int conversion failed: invalid literal for int() with base 10: 'keep')`
- input: `not-a-number`
- output: `Ok(value='keep')` (Ok)

#### `try raise: the default behaviour of a failing stage` — guard
- tier ★★★ Core
- note: UP2-E2005: the run fails
- chain:
  - `["py", "const", "keep"]` → `Ok(value='keep')`
  - `["try", "raise"]` → `(a directive: it does no work)`
  - `["py", "int"]` → `Failed(UP2-E2005: py.int conversion failed: invalid literal for int() with base 10: 'keep')`
- input: `not-a-number`
- output: `Failed(code='UP2-E2005', reason="py.int conversion failed: invalid literal for int() with base 10: 'keep'", fix='py.int expects an integer, a float, a bool, or a string of digits; …` (Failed)

#### `a guarded success disarms the guard` — guard
- tier ★★★ Core
- note: the guard covered one stage only: the later failure still fails the run
- chain:
  - `["py", "const", ""]` → `Ok(value='')`
  - `["try", "skip"]` → `(a directive: it does no work)`
  - `["py", "strip"]` → `Ok(value='')`
  - `["py", "int"]` → `Failed(UP2-E2005: py.int conversion failed: invalid literal for int() with base 10: '')`
- input: `not-a-number`
- output: `Failed(code='UP2-E2005', reason="py.int conversion failed: invalid literal for int() with base 10: ''", fix='py.int expects an integer, a float, a bool, or a string of digits; chec…` (Failed)

### D. Invalid forms owned by no operator

| invalid chain | code | pointer | message | fix |
|---|---|---|---|---|
| `[["nope", "strip", ""]]` | `UP2-E1001` | `/0/0` | unknown operator 'nope' | use one of the following operators |


## The host side: fetching a page

The kernel never fetches anything: a story calls a host `fetch` function, and the **host** answers. The package offers a default for that side — a synchronous, standard-library downloader and a request cache under `.cache/requests/` (never committed), keyed by the whole request. A body is binary, so the request carries it as **base64 text**.

```python
from uniparser2.net import RequestCache, fetch

cache = RequestCache()
answer = cache.get(request) or fetch(request)   # a miss is a miss
cache.put(request, answer)                      # → Response(text=…, url=…)
```

The request is an ordinary object a chain builds: `url` (required), `method`, `headers`, `timeout`, `params`, and a body that is `body` (base64) or `json`. The `up2 snapshot` / `up2 test` runner replays the cached answers, so a chain that fetches can be frozen and regressed **offline**; a request with no cached answer is a miss, and the runner never reaches the network.
