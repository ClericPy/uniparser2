# uniparser2 parsing-chain report

Input → triple chain → output repr: every entry below is the result of a **real run** (`uv run python tools/demo_report.py --md`). This file is generated — regenerate it after changing an operator; `--md --check` fails when it is stale. The local HTML build (`.cache/report/up2-report.html`) shows installed/missing dependency state and is not committed.

Generated from `uniparser2` 0.5.0 · one case per `(operator, action)` pair declared by the registry, plus multi-stage compositions, the shared mechanisms and the compile-time invalid forms.

## Coverage check

- **Coverage check passed**: every declared pair has a case and every behavior case ran `Ok`.
- the registry declares **73** pairs = **73** pairs covered by cases
- states across every run: `Failed` 7, `Missing` 1, `Ok` 98

| operator | arity | slots | summary | actions |
|---|---|---|---|---|
| `css` | 3 | accessor / selector | CSS selector (all matches) | 8 |
| `css1` | 3 | accessor / selector | CSS selector (first match only) | 8 |
| `py` | 3 | function / params | Python built-in allowlist functions | 42 |
| `xpath` | 3 | accessor / XPath | XPath query (XML; lxml) | 3 |
| `json` | 2 | jmespath path | JSON dot-path query (jmespath) | 1 |
| `re` | 3 | mode / pattern | Regex matching (search / group / findall) | 3 |
| `ctx` | 3 | action / parameter | Scope reads and writes (get / set / del / map) | 4 |
| `const` | 2 | value | Literal (never resolved as a reference) | 1 |
| `code` | 2 | source & inputs | In-chain code (sandboxed; optional dependency [code]) | 1 |
| `udf` | 3 | action / parameter | Host-registered named function (the chain carries no code) | 1 |
| `each` | 2 | fields | One dictionary per element of a list | 1 |


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

Shared input for this section:

```text
'\n<html>\n  <head>\n    <meta name="PubDate" content="2026-09-24 15:30:00">\n    <title>Notice on Issuing the Government Service Item List</title>\n  </head>\n  <body>\n    <h1 cl…
```

### Actions (sorted by commonness)

#### `text` — plain text
- tier ★★★ Core · parameter slot: the value itself · `selector: literal`
- note: plain text (no script/style/noscript)
- chain: `[["css", "text", "h1.article-title"]]`
- input: the shared sample above
- output: `Ok(value=['  Notice on Issuing the Government Service Item List  '])` (Ok)

#### `@<attribute>` — attribute value
- tier ★★★ Core · parameter slot: the value itself · `attr: literal`, `selector: literal`
- note: attribute value; absent ⇒ Missing
- chain: `[["css", "@href", "a.download"]]`
- input: the shared sample above
- output: `Ok(value=['/files/list.pdf'])` (Ok)

#### `html` — inner HTML
- tier ★★ Common · parameter slot: the value itself · `selector: literal`
- note: inner HTML
- chain: `[["css", "html", "div.content"]]`
- input: the shared sample above
- output: `Ok(value=['\n      <script>console.log(\'this script must not reach the body\');</script>\n      <p>To all municipal governments:</p>\n      <p>The Government Service Item List is …` (Ok)

#### `remove` — a copy with the matching nodes pruned
- tier ★★ Common · parameter slot: the value itself · `selector: literal`
- note: pure function: pruned copy
- chain: `[["css", "remove", "script,style"]]`
- input: the shared sample above
- output: `Ok(value=<DomNode HTMLParser>)` (Ok)

#### `nodes` — the set of matching nodes
- tier ★★ Common · parameter slot: the value itself · `selector: literal`
- note: node set for L2 fan-out (not a value)
- chain: `[["css", "nodes", "ul.rel a"]]`
- input: the shared sample above
- output: `Ok(value=[<DomNode Node>, <DomNode Node>])` (Ok)

#### `exists` — whether the selector matches at least one node
- tier ★★ Common · parameter slot: the value itself · `selector: literal`
- note: boolean: does the selector match
- chain: `[["css", "exists", "ul.rel a"]]`
- input: the shared sample above
- output: `Ok(value=True)` (Ok)

#### `outer` — outer HTML
- tier ★ Advanced · parameter slot: the value itself · `selector: literal`
- note: outer HTML (with its own tag)
- chain: `[["css", "outer", "h1.article-title"]]`
- input: the shared sample above
- output: `Ok(value=['<h1 class="article-title">  Notice on Issuing the Government Service Item List  </h1>'])` (Ok)

#### `self` — the node handle itself
- tier ★ Advanced · parameter slot: the value itself · `selector: literal`
- note: handle of the first match
- chain: `[["css", "self", "div.content"]]`
- input: the shared sample above
- output: `Ok(value=<DomNode Node>)` (Ok)

### Compositions (multi-stage chains)

#### `composition` — css
- tier ★★★ Core
- note: prune → take HTML → convert to Markdown (the standard body-extraction trio)
- chain:
  - `["css", "remove", "script,style"]` → `Ok(value=<DomNode HTMLParser>)`
  - `["css1", "html", "div.content"]` → `Ok(value='\n      \n      <p>To all municipal governments:</p>\n      <p>The Government Service Item List is hereby issued to you; please comply.</p>\n      <a class="download" hre…`
  - `["py", "html_to_markdown", ""]` → `Ok(value='To all municipal governments:\n\nThe Government Service Item List is hereby issued to you; please comply.\n\n[Download the list](/files/list.pdf)\n')`
- input: `'\n<html>\n  <head>\n    <meta name="PubDate" content="2026-09-24 15:30:00">\n    <title>Notice on Issuing the Government Service Item List</title>\n  </head>\n  <body>\n    <h1 cl…`
- output: `Ok(value='To all municipal governments:\n\nThe Government Service Item List is hereby issued to you; please comply.\n\n[Download the list](/files/list.pdf)\n')` (Ok)

#### `composition` — css
- tier ★★★ Core
- note: css yields a list: every href at once
- chain: `[["css", "@href", "ul.rel a"]]`
- input: `'\n<html>\n  <head>\n    <meta name="PubDate" content="2026-09-24 15:30:00">\n    <title>Notice on Issuing the Government Service Item List</title>\n  </head>\n  <body>\n    <h1 cl…`
- output: `Ok(value=['/p/1.html', '/p/2.html'])` (Ok)

#### `composition` — css
- tier ★★★ Core
- note: node set → count
- chain:
  - `["css", "nodes", "ul.rel a"]` → `Ok(value=[<DomNode Node>, <DomNode Node>])`
  - `["py", "len", ""]` → `Ok(value=2)`
- input: `'\n<html>\n  <head>\n    <meta name="PubDate" content="2026-09-24 15:30:00">\n    <title>Notice on Issuing the Government Service Item List</title>\n  </head>\n  <body>\n    <h1 cl…`
- output: `Ok(value=2)` (Ok)

#### `composition` — css
- tier ★★★ Core
- note: node set → one dictionary per list item (each): the per-item shape
- chain:
  - `["css", "nodes", "ul.rel li"]` → `Ok(value=[<DomNode Node>, <DomNode Node>])`
  - `["each", {"title": [["css1", "text", "a"]], "href": [["css1", "@href", "a"]]}]` → `Ok(value=[{'title': 'Related one', 'href': '/p/1.html'}, {'title': 'Related two', 'href': '/p/2.html'}])`
- input: `'\n<html>\n  <head>\n    <meta name="PubDate" content="2026-09-24 15:30:00">\n    <title>Notice on Issuing the Government Service Item List</title>\n  </head>\n  <body>\n    <h1 cl…`
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

Shared input for this section:

```text
'\n<html>\n  <head>\n    <meta name="PubDate" content="2026-09-24 15:30:00">\n    <title>Notice on Issuing the Government Service Item List</title>\n  </head>\n  <body>\n    <h1 cl…
```

### Actions (sorted by commonness)

#### `text` — plain text
- tier ★★★ Core · parameter slot: the value itself · `selector: literal`
- note: plain text (no script/style/noscript)
- chain: `[["css1", "text", "h1.article-title"]]`
- input: the shared sample above
- output: `Ok(value='  Notice on Issuing the Government Service Item List  ')` (Ok)

#### `@<attribute>` — attribute value
- tier ★★★ Core · parameter slot: the value itself · `attr: literal`, `selector: literal`
- note: attribute value; absent ⇒ Missing
- chain: `[["css1", "@href", "a.download"]]`
- input: the shared sample above
- output: `Ok(value='/files/list.pdf')` (Ok)

#### `html` — inner HTML
- tier ★★ Common · parameter slot: the value itself · `selector: literal`
- note: inner HTML
- chain: `[["css1", "html", "div.content"]]`
- input: the shared sample above
- output: `Ok(value='\n      <script>console.log(\'this script must not reach the body\');</script>\n      <p>To all municipal governments:</p>\n      <p>The Government Service Item List is h…` (Ok)

#### `remove` — a copy with the matching nodes pruned
- tier ★★ Common · parameter slot: the value itself · `selector: literal`
- note: pure function: pruned copy
- chain: `[["css1", "remove", "script,style"]]`
- input: the shared sample above
- output: `Ok(value=<DomNode HTMLParser>)` (Ok)

#### `nodes` — the set of matching nodes
- tier ★★ Common · parameter slot: the value itself · `selector: literal`
- note: node set for L2 fan-out (not a value)
- chain: `[["css1", "nodes", "ul.rel a"]]`
- input: the shared sample above
- output: `Ok(value=[<DomNode Node>])` (Ok)

#### `exists` — whether the selector matches at least one node
- tier ★★ Common · parameter slot: the value itself · `selector: literal`
- note: boolean: does the selector match
- chain: `[["css1", "exists", "ul.rel a"]]`
- input: the shared sample above
- output: `Ok(value=True)` (Ok)

#### `outer` — outer HTML
- tier ★ Advanced · parameter slot: the value itself · `selector: literal`
- note: outer HTML (with its own tag)
- chain: `[["css1", "outer", "h1.article-title"]]`
- input: the shared sample above
- output: `Ok(value='<h1 class="article-title">  Notice on Issuing the Government Service Item List  </h1>')` (Ok)

#### `self` — the node handle itself
- tier ★ Advanced · parameter slot: the value itself · `selector: literal`
- note: handle of the first match
- chain: `[["css1", "self", "div.content"]]`
- input: the shared sample above
- output: `Ok(value=<DomNode Node>)` (Ok)

### Compositions (multi-stage chains)

#### `composition` — css1
- tier ★★★ Core
- note: take the heading → normalize whitespace
- chain:
  - `["css1", "text", "h1.article-title"]` → `Ok(value='  Notice on Issuing the Government Service Item List  ')`
  - `["py", "normalize_space", ""]` → `Ok(value='Notice on Issuing the Government Service Item List')`
- input: `'\n<html>\n  <head>\n    <meta name="PubDate" content="2026-09-24 15:30:00">\n    <title>Notice on Issuing the Government Service Item List</title>\n  </head>\n  <body>\n    <h1 cl…`
- output: `Ok(value='Notice on Issuing the Government Service Item List')` (Ok)

#### `composition` — css1
- tier ★★★ Core
- note: take the attribute → build the absolute URL
- chain:
  - `["css1", "@href", "a.download"]` → `Ok(value='/files/list.pdf')`
  - `["py", "urljoin", "https://x/p/"]` → `Ok(value='https://x/files/list.pdf')`
- input: `'\n<html>\n  <head>\n    <meta name="PubDate" content="2026-09-24 15:30:00">\n    <title>Notice on Issuing the Government Service Item List</title>\n  </head>\n  <body>\n    <h1 cl…`
- output: `Ok(value='https://x/files/list.pdf')` (Ok)

#### `composition` — css
- tier ★★★ Core
- note: extract → process in the sandbox (allowlisted functions need no import)
- chain:
  - `["css1", "text", "h1.article-title"]` → `Ok(value='  Notice on Issuing the Government Service Item List  ')`
  - `["code", {"src": "normalize_space(obj)"}]` → `Ok(value='Notice on Issuing the Government Service Item List')`
- input: `'\n<html>\n  <head>\n    <meta name="PubDate" content="2026-09-24 15:30:00">\n    <title>Notice on Issuing the Government Service Item List</title>\n  </head>\n  <body>\n    <h1 cl…`
- output: `Ok(value='Notice on Issuing the Government Service Item List')` (Ok)


## `py` — Python built-in allowlist functions

arity 3 · slot 2=function / slot 3=params · dependencies: none · 42 actions (Core, Common, Advanced, Rare)

Shared input for this section:

```text
'  text  '
```

### Actions (sorted by commonness)

#### `strip` — strip leading and trailing whitespace
- tier ★★★ Core · parameter slot: no parameter (write two positions, or "")
- note: strip leading/trailing whitespace
- chain: `[["py", "strip", ""]]`
- input: the shared sample above
- output: `Ok(value='text')` (Ok)

#### `normalize_space` — collapse runs of whitespace into a single space
- tier ★★★ Core · parameter slot: no parameter (write two positions, or "")
- note: collapse consecutive whitespace
- chain: `[["py", "normalize_space", ""]]`
- input: `'a   b\n c'`
- output: `Ok(value='a b c')` (Ok)

#### `urljoin` — resolve relative to absolute
- tier ★★★ Core · parameter slot: the value itself · `base: ref_or_literal`
- note: relative to absolute (pass base)
- chain: `[["py", "urljoin", "https://x/p/"]]`
- input: `'a.html'`
- output: `Ok(value='https://x/p/a.html')` (Ok)

#### `first` — take the first element
- tier ★★★ Core · parameter slot: no parameter (write two positions, or "")
- note: first item (xpath/css yield a list; a scalar is needed)
- chain: `[["py", "first", ""]]`
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

#### `id` — return the input unchanged (a step whose value is its own input)
- tier ★★★ Core · parameter slot: no parameter (write two positions, or "")
- note: identity: the input unchanged
- chain: `[["py", "id", ""]]`
- input: `'https://example.com/list.html'`
- output: `Ok(value='https://example.com/list.html')` (Ok)

#### `len` — length
- tier ★★★ Core · parameter slot: no parameter (write two positions, or "")
- note: length
- chain: `[["py", "len", ""]]`
- input: `[1, 2, 3]`
- output: `Ok(value=3)` (Ok)

#### `slice` — slice a string or list
- tier ★★★ Core · parameter slot: the value itself · `spec: literal`
- note: slice: ":3" / "1:5" / "::-1"
- chain: `[["py", "slice", ":3"]]`
- input: `'abcdef'`
- output: `Ok(value='abc')` (Ok)

#### `default` — fall back when empty/None/missing
- tier ★★★ Core · parameter slot: the value itself · `value: ref_or_literal`
- note: fallback for empty/None/missing (accepts_missing)
- chain: `[["py", "default", "fallback value"]]`
- input: `''`
- output: `Ok(value='fallback value')` (Ok)

#### `getitem` — take a subscript: a sequence index, a mapping key or a str character
- tier ★★ Common · parameter slot: the value itself · `at: ref_or_literal`
- note: list index (out of range ⇒ UP2-E2018)
- chain: `[["py", "getitem", 1]]`
- input: `['a', 'b']`
- output: `Ok(value='b')` (Ok)

#### `last` — take the last element
- tier ★★ Common · parameter slot: no parameter (write two positions, or "")
- note: last item
- chain: `[["py", "last", ""]]`
- input: `[1, 2]`
- output: `Ok(value=2)` (Ok)

#### `replace` — replace all occurrences
- tier ★★ Common · parameter slot: a named object (a positional array also works) · `old: literal`, `new: literal`
- note: replace all (positional array)
- chain: `[["py", "replace", ["old", "new"]]]`
- input: `'old document'`
- output: `Ok(value='new document')` (Ok)

#### `split` — split on a separator
- tier ★★ Common · parameter slot: a named object (a positional array also works) · `sep: literal`, `maxsplit: literal?, default None`
- note: split on a separator
- chain: `[["py", "split", ","]]`
- input: `'a,b,c'`
- output: `Ok(value=['a', 'b', 'c'])` (Ok)

#### `join` — join a list
- tier ★★ Common · parameter slot: the value itself · `sep: literal`
- note: join a list
- chain: `[["py", "join", "-"]]`
- input: `['a', 'b']`
- output: `Ok(value='a-b')` (Ok)

#### `strip_tags` — remove HTML tags
- tier ★★ Common · parameter slot: no parameter (write two positions, or "")
- note: strip HTML tags
- chain: `[["py", "strip_tags", ""]]`
- input: `'<b>text</b>'`
- output: `Ok(value='text')` (Ok)

#### `parse_time` — parse a time string into the canonical format %Y-%m-%d %H:%M:%S (explicit format, the built-in table, then natural-language detection)
- tier ★★ Common · parameter slot: a named object (a positional array also works) · `lang: literal?, default None`, `format: literal?, default None`, `date_order: literal?, default None`, `now: ref_or_literal?, default None`
- note: time normalization (0 required dependencies)
- chain: `[["py", "parse_time", ""]]`
- input: `'2026-09-24 15:30:00'`
- output: `Ok(value='2026-09-24 15:30:00')` (Ok)

#### `strftime` — render the canonical time string in another layout (%Y-%m-%d %H:%M:%S → %Y/%m/%d)
- tier ★★ Common · parameter slot: the value itself · `layout: literal`
- note: render the canonical time in another layout (output side)
- chain: `[["py", "strftime", "%Y/%m/%d"]]`
- input: `'2026-09-24 15:30:00'`
- output: `Ok(value='2026/09/24')` (Ok)

#### `html_to_markdown` — HTML → Markdown (no parameters; complete relative links with py.urljoin)
- tier ★★ Common · parameter slot: no parameter (write two positions, or "")
- note: optional dependency [md]
- chain: `[["py", "html_to_markdown", ""]]`
- input: `'<h1>Heading</h1><p>a <b>b</b></p>'`
- output: `Ok(value='# Heading\n\na **b**\n')` (Ok)

#### `int` — convert to an integer (former cast int)
- tier ★★ Common · parameter slot: no parameter (write two positions, or "")
- note: type conversion (formerly cast int)
- chain: `[["py", "int", ""]]`
- input: `'42'`
- output: `Ok(value=42)` (Ok)

#### `str` — convert to a string (former cast str)
- tier ★★ Common · parameter slot: no parameter (write two positions, or "")
- note: type conversion (formerly cast str)
- chain: `[["py", "str", ""]]`
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
- input: `'200'`
- output: `Ok(value=True)` (Ok)

#### `in` — is the value in the parameter (Python's in: the parameter is the container)
- tier ★★ Common · parameter slot: the value itself · `container: ref_or_literal`
- note: Python's in: the parameter is the container
- chain: `[["py", "in", [200, 301, 302]]]`
- input: `301`
- output: `Ok(value=True)` (Ok)

#### `or` — the first truthy operand, else the last (Python's or; answers with the operand)
- tier ★★ Common · parameter slot: the value itself · `operands: ref_or_literal`
- note: Python's or: first truthy, else the last
- chain: `[["py", "or", ["", "fallback"]]]`
- input: `'in'`
- output: `Ok(value='fallback')` (Ok)

#### `and` — the first falsy operand, else the last (Python's and)
- tier ★★ Common · parameter slot: the value itself · `operands: ref_or_literal`
- note: Python's and: first falsy, else the last
- chain: `[["py", "and", [{"a": 1}, ""]]]`
- input: `'in'`
- output: `Ok(value='')` (Ok)

#### `upper` — convert to uppercase
- tier ★ Advanced · parameter slot: no parameter (write two positions, or "")
- note: uppercase
- chain: `[["py", "upper", ""]]`
- input: `'abc'`
- output: `Ok(value='ABC')` (Ok)

#### `lower` — convert to lowercase
- tier ★ Advanced · parameter slot: no parameter (write two positions, or "")
- note: lowercase
- chain: `[["py", "lower", ""]]`
- input: `'ABC'`
- output: `Ok(value='abc')` (Ok)

#### `flatten` — flatten one level
- tier ★ Advanced · parameter slot: no parameter (write two positions, or "")
- note: flatten one level
- chain: `[["py", "flatten", ""]]`
- input: `[[1, 2], [3]]`
- output: `Ok(value=[1, 2, 3])` (Ok)

#### `sort` — stable sort
- tier ★ Advanced · parameter slot: a named object (a positional array also works) · `key: literal?, default None`, `reverse: literal?, default False`
- note: stable sort
- chain: `[["py", "sort", ""]]`
- input: `[3, 1, 2]`
- output: `Ok(value=[1, 2, 3])` (Ok)

#### `uniq` — deduplicate while preserving order
- tier ★ Advanced · parameter slot: no parameter (write two positions, or "")
- note: deduplicate, keeping order
- chain: `[["py", "uniq", ""]]`
- input: `[1, 1, 2]`
- output: `Ok(value=[1, 2])` (Ok)

#### `urlsplit` — split a URL into parts
- tier ★ Advanced · parameter slot: the value itself · `part: literal`
- note: URL parts (take the site identity)
- chain: `[["py", "urlsplit", "netloc"]]`
- input: `'https://x/a?q=1'`
- output: `Ok(value='x')` (Ok)

#### `b64_decode` — Base64 decode
- tier ★ Advanced · parameter slot: no parameter (write two positions, or "")
- note: Base64 decode
- chain: `[["py", "b64_decode", ""]]`
- input: `'YWJj'`
- output: `Ok(value='abc')` (Ok)

#### `sha256` — hexadecimal digest
- tier ★ Advanced · parameter slot: no parameter (write two positions, or "")
- note: hex digest (idempotency key)
- chain: `[["py", "sha256", ""]]`
- input: `'abc'`
- output: `Ok(value='ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')` (Ok)

#### `from_json` — JSON text → JSON tree (former cast json)
- tier ★ Advanced · parameter slot: no parameter (write two positions, or "")
- note: JSON text → JSON tree (formerly cast json)
- chain: `[["py", "from_json", ""]]`
- input: `'{"a": 1}'`
- output: `Ok(value={'a': 1})` (Ok)

#### `float` — convert to a float (former cast float)
- tier ★ Advanced · parameter slot: no parameter (write two positions, or "")
- note: type conversion
- chain: `[["py", "float", ""]]`
- input: `'1.5'`
- output: `Ok(value=1.5)` (Ok)

#### `bool` — convert to a boolean (former cast bool)
- tier ★ Advanced · parameter slot: no parameter (write two positions, or "")
- note: type conversion (falsey word list)
- chain: `[["py", "bool", ""]]`
- input: `'no'`
- output: `Ok(value=False)` (Ok)

#### `list` — convert to a list (JSON array text or as-is)
- tier ★ Advanced · parameter slot: no parameter (write two positions, or "")
- note: JSON array text → list
- chain: `[["py", "list", ""]]`
- input: `'["a","b"]'`
- output: `Ok(value=['a', 'b'])` (Ok)

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
- input: `'c'`
- output: `Ok(value=True)` (Ok)

#### `b64_encode` — Base64 encode
- tier ○ Rare · parameter slot: no parameter (write two positions, or "")
- note: Base64 encode
- chain: `[["py", "b64_encode", ""]]`
- input: `'abc'`
- output: `Ok(value='YWJj')` (Ok)

### Compositions (multi-stage chains)

#### `composition` — py
- tier ★★★ Core
- note: normalize to the canonical time → render another layout (the output side)
- chain:
  - `["py", "parse_time", ""]` → `Ok(value='2026-09-24 15:30:00')`
  - `["py", "strftime", "%Y/%m/%d"]` → `Ok(value='2026/09/24')`
- input: `'2026-09-24 15:30:00'`
- output: `Ok(value='2026/09/24')` (Ok)

#### `composition` — py
- tier ★★★ Core
- note: parse the JSON text first, then use the json operator to take a subtree
- chain:
  - `["py", "from_json", ""]` → `Ok(value={'data': {'html': '<p>Body</p>', 'list': [{'url': 'u1'}, {'url': 'u2'}]}})`
  - `["json", "data.html"]` → `Ok(value='<p>Body</p>')`
- input: `'{"data": {"html": "<p>Body</p>", "list": [{"url": "u1"}, {"url": "u2"}]}}'`
- output: `Ok(value='<p>Body</p>')` (Ok)

#### `composition` — py
- tier ★★★ Core
- note: a parameter referencing globals
- chain: `[["py", "urljoin", "$globals.base"]]`
- input: `'a.html'`
- output: `Ok(value='https://example.gov.cn/p/a.html')` (Ok)

#### `composition` — py
- tier ★★★ Core
- note: convert → regex → convert again
- chain:
  - `["py", "str", ""]` → `Ok(value='2026')`
  - `["re", "search", "\\d+"]` → `Ok(value='2026')`
  - `["py", "int", ""]` → `Ok(value=2026)`
- input: `2026`
- output: `Ok(value=2026)` (Ok)

#### `composition` — py
- tier ★★★ Core
- note: time normalization → take the date part
- chain:
  - `["py", "parse_time", ""]` → `Ok(value='2026-09-24 15:30:00')`
  - `["py", "slice", ":10"]` → `Ok(value='2026-09-24')`
- input: `'2026/09/24 15:30:00'`
- output: `Ok(value='2026-09-24')` (Ok)

### Invalid forms

| invalid chain | code | pointer | message | fix |
|---|---|---|---|---|
| `[["py", "strip"]]` | `UP2-E1004` | `/0` | py needs 3 slots, got 2 | this operator's slots are slot2=function, slot3=params; for an action with no parameters, write "" in slot 3 |
| `[["py", "strip", "", ""]]` | `UP2-E1004` | `/0` | stage length is 4, only 2 or 3 is allowed | follow the declared arity: 3 slots is ["operator", slot2, slot3]; 2 slots is ["operator", parameter] |
| `[["py", "no_such_function", ""]]` | `UP2-E1003` | `/0/1` | the py allowlist has no function 'no_such_function' | use one of the functions below (run up2 ops --json for the full table) |
| `[["py", "parse_time", {"format": "%Q"}]]` | `UP2-E1005` | `/0/2/format` | invalid strptime format: 'Q' is a bad directive in format '%Q' | fix the directives in format |
| `[["py", "default", "$nope.x"]]` | `UP2-E1006` | `/0/2` | unknown reference root 'nope' | use a reserved root, or declare the earlier node product with --product |
| `[["py", "urljoin", {"base": "https://example.com/news/"}]]` | `UP2-E1005` | `/0/2/base` | parameter 'base' of py.urljoin must be a string, got dict | write the value directly: ["py", "urljoin", "…"] |
| `[["py", "slice", {"spec": "0:4"}]]` | `UP2-E1005` | `/0/2/spec` | parameter 'spec' of py.slice must be a string, got dict | write the value directly: ["py", "slice", "…"] |
| `[["py", "getitem", {"at": {}}]]` | `UP2-E1005` | `/0/2/at` | parameter 'at' of py.getitem must be a scalar, got dict | write the value directly: ["py", "getitem", "…"] |
| `[["py", "split", {"sep": ",", "maxsplit": {}}]]` | `UP2-E1005` | `/0/2/maxsplit` | parameter 'maxsplit' of py.split must be an integer, got dict | write the parameters as a named object with 'sep', 'maxsplit', for example {"maxsplit": …} |
| `[["py", "sort", {"key": {}}]]` | `UP2-E1005` | `/0/2/key` | the key of sort must be one of ('', 'str', 'int', 'float'), got {} | write "str", "int" or "float", or drop the parameter |


## `xpath` — XPath query (XML; lxml)

arity 3 · slot 2=accessor / slot 3=XPath · dependencies: `lxml` · 3 actions (Core, Common, Advanced)

Shared input for this section:

```text
'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n  <url><loc>https://x/1</loc><lastmod>2026-09-23</lastmod></url>\n  <url><loc…
```

### Actions (sorted by commonness)

#### `text` — text value (elements: all descendant text; attributes as-is)
- tier ★★★ Core · parameter slot: a named object (a positional array also works) · `expr: literal`, `ns: literal?, default None`
- chain: `[["xpath", "text", "//*[local-name()='loc']"]]`
- input: the shared sample above
- output: `Ok(value=['https://x/1', 'https://x/2'])` (Ok)

#### `nodes` — the set of matching nodes
- tier ★★ Common · parameter slot: a named object (a positional array also works) · `expr: literal`, `ns: literal?, default None`
- chain: `[["xpath", "nodes", "//*[local-name()='url']"]]`
- input: the shared sample above
- output: `Ok(value=[<XPathNode {http://www.sitemaps.org/schemas/sitemap/0.9}url>, <XPathNode {http://www.sitemaps.org/schemas/sitemap/0.9}url>])` (Ok)

#### `self` — the first matching node (relative paths can keep selecting)
- tier ★ Advanced · parameter slot: a named object (a positional array also works) · `expr: literal`, `ns: literal?, default None`
- chain: `[["xpath", "self", "//*[local-name()='url']"]]`
- input: the shared sample above
- output: `Ok(value=<XPathNode {http://www.sitemaps.org/schemas/sitemap/0.9}url>)` (Ok)

### Compositions (multi-stage chains)

#### `composition` — xpath
- tier ★★★ Core
- note: sitemap: every lastmod → take the last
- chain:
  - `["xpath", "text", "//*[local-name()='lastmod']"]` → `Ok(value=['2026-09-23', '2026-09-24'])`
  - `["py", "last", ""]` → `Ok(value='2026-09-24')`
- input: `'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n  <url><loc>https://x/1</loc><lastmod>2026-09-23</lastmod></url>\n  <url><loc…`
- output: `Ok(value='2026-09-24')` (Ok)

#### `composition` — xpath
- tier ★★★ Core
- note: namespace prefix: slot 3 takes an object form carrying the ns map
- chain: `[["xpath", "text", {"expr": "//dc:creator", "ns": {"dc": "http://purl.org/dc/elements/1.1/"}}]]`
- input: `'<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/">\n  <channel><item><title>Headline</title><dc:creator>Jane Reporter</dc:crea…`
- output: `Ok(value=['Jane Reporter'])` (Ok)

### Invalid forms

| invalid chain | code | pointer | message | fix |
|---|---|---|---|---|
| `[["xpath", "text", "//dc:creator"]]` | `UP2-E1005` | `/0/2/expr` | the XPath expression is unusable: Undefined namespace prefix | fix expr; provide an ns mapping, e.g. {"dc": "http://purl.org/dc/elements/1.1/"} |


## `json` — JSON dot-path query (jmespath)

arity 2 · slot 2=jmespath path · dependencies: `jmespath` · 1 actions (Core)

Shared input for this section:

```text
'{"data": {"html": "<p>Body</p>", "list": [{"url": "u1"}, {"url": "u2"}]}}'
```

### Actions (sorted by commonness)

#### `get` — jmespath query (empty expression = the root)
- tier ★★★ Core · parameter slot: the value itself · `expr: literal?, default ''`
- note: 2 positions: action slot omitted
- chain: `[["json", "data.list[*].url"]]`
- input: the shared sample above
- output: `Ok(value=['u1', 'u2'])` (Ok)

### Compositions (multi-stage chains)

#### `composition` — json
- tier ★★★ Core
- note: take all URLs → take the first
- chain:
  - `["json", "data.list[*].url"]` → `Ok(value=['u1', 'u2'])`
  - `["py", "first", ""]` → `Ok(value='u1')`
- input: `'{"data": {"html": "<p>Body</p>", "list": [{"url": "u1"}, {"url": "u2"}]}}'`
- output: `Ok(value='u1')` (Ok)

### Invalid forms

| invalid chain | code | pointer | message | fix |
|---|---|---|---|---|
| `[["json", "("]]` | `UP2-E1005` | `/0/1/expr` | invalid jmespath expression: Invalid jmespath expression: Incomplete expression:<br>"("<br>  ^ | fix the path (e.g. data.list[*].url, data.html, or an empty string for the root) |


## `re` — Regex matching (search / group / findall)

arity 3 · slot 2=mode / slot 3=pattern · dependencies: none · 3 actions (Core, Common, Advanced)

Shared input for this section:

```text
'published 2026-09-24 end'
```

### Actions (sorted by commonness)

#### `search` — the whole first match group(0)
- tier ★★★ Core · parameter slot: the value itself · `pattern: literal`
- chain: `[["re", "search", "\\d{4}-\\d{2}-\\d{2}"]]`
- input: the shared sample above
- output: `Ok(value='2026-09-24')` (Ok)

#### `group` — take the given capture group
- tier ★★ Common · parameter slot: a named object (a positional array also works) · `pattern: literal`, `group: literal`
- note: named object: pattern + group
- chain: `[["re", "group", {"pattern": "(\\d{4})-(\\d{2})", "group": 2}]]`
- input: `'2026-09'`
- output: `Ok(value='09')` (Ok)

#### `findall` — findall: every match
- tier ★ Advanced · parameter slot: the value itself · `pattern: literal`
- chain: `[["re", "findall", "\\d+"]]`
- input: `'a1b22c333'`
- output: `Ok(value=['1', '22', '333'])` (Ok)

### Compositions (multi-stage chains)

#### `composition` — re
- tier ★★★ Core
- note: whole text → the year inside it
- chain:
  - `["re", "search", "\\d{4}-\\d{2}-\\d{2}"]` → `Ok(value='2026-09-24')`
  - `["re", "search", "\\d{4}"]` → `Ok(value='2026')`
- input: `'published 2026-09-24 end'`
- output: `Ok(value='2026')` (Ok)

### Invalid forms

| invalid chain | code | pointer | message | fix |
|---|---|---|---|---|
| `[["re", "group", {"pattern": "a", "group": 9}]]` | `UP2-E1005` | `/0/2/group` | the pattern has only 0 capture groups, so group 9 is unavailable | change the group index, or add a capture group to the pattern |


## `ctx` — Scope reads and writes (get / set / del / map)

arity 3 · slot 2=action / slot 3=parameter · dependencies: none · 4 actions (Common, Advanced, Rare)

Shared input for this section:

```text
None
```

### Actions (sorted by commonness)

#### `get` — read a scope path
- tier ★★ Common · parameter slot: the value itself · `path: literal`
- chain: `[["ctx", "get", "locals.k"]]`
- input: the shared sample above
- output: `Ok(value='local value')` (Ok)

#### `set` — write the upstream value into locals
- tier ★★ Common · parameter slot: the value itself · `path: literal`
- note: the write surface is limited to locals/fields
- chain: `[["ctx", "set", "locals.k"]]`
- input: `'written value'`
- output: `Ok(value='written value')` (Ok)

#### `map` — collect several values into a list or a dict
- tier ★ Advanced · parameter slot: the value itself · `refs: literal`
- note: named-object form → dict
- chain: `[["ctx", "map", {"a": "locals.x", "b": "locals.y"}]]`
- input: the shared sample above
- output: `Ok(value={'a': 1, 'b': 2})` (Ok)

#### `del` — delete a path in locals
- tier ○ Rare · parameter slot: the value itself · `path: literal`
- chain: `[["ctx", "del", "locals.k"]]`
- input: `'upstream value'`
- output: `Ok(value='upstream value')` (Ok)

### Compositions (multi-stage chains)

#### `composition` — ctx
- tier ★★★ Core
- note: write to locals → read back (the `_` prefix = internal path)
- chain:
  - `["ctx", "set", "locals._tmp"]` → `Ok(value='intermediate value')`
  - `["ctx", "get", "locals._tmp"]` → `Ok(value='intermediate value')`
- input: `'intermediate value'`
- output: `Ok(value='intermediate value')` (Ok)

### Invalid forms

| invalid chain | code | pointer | message | fix |
|---|---|---|---|---|
| `[["ctx", "set", "globals.x"]]` | `UP2-E1015` | `/0/2/path` | ctx.set cannot write 'globals.x' | the write surface is limited to locals.* / fields.* (globals and node output are read-only) |


## `const` — Literal (never resolved as a reference)

arity 2 · slot 2=value · dependencies: none · 1 actions (Core)

Shared input for this section:

```text
'\n<html>\n  <head>\n    <meta name="PubDate" content="2026-09-24 15:30:00">\n    <title>Notice on Issuing the Government Service Item List</title>\n  </head>\n  <body>\n    <h1 cl…
```

### Actions (sorted by commonness)

#### `const` — Produce the value verbatim
- tier ★★★ Core · parameter slot: the value itself · `value: literal`
- note: 2 positions: literal
- chain: `[["const", "article"]]`
- input: the shared sample above
- output: `Ok(value='article')` (Ok)


## `code` — In-chain code (sandboxed; optional dependency [code])

arity 2 · slot 2=source & inputs · dependencies: `pydantic_monty` · 1 actions (Advanced)

Shared input for this section:

```text
'\n<html>\n  <head>\n    <meta name="PubDate" content="2026-09-24 15:30:00">\n    <title>Notice on Issuing the Government Service Item List</title>\n  </head>\n  <body>\n    <h1 cl…
```

### Actions (sorted by commonness)

#### `run` — run src once and take the value of the last expression
- tier ★ Advanced · parameter slot: a named object (a positional array also works) · `src: literal`, `inputs: ref_or_literal?, default None`
- note: sandboxed; optional dependency [code]; the last expression value is returned
- chain: `[["code", {"src": "ctx.locals.prefix + normalize_space(obj)"}]]`
- input: the shared sample above
- output: `Ok(value='Title: <html> <head> <meta name="PubDate" content="2026-09-24 15:30:00"> <title>Notice on Issuing the Government Service Item List</title> </head> <body> <h1 class="artic…` (Ok)


## `udf` — Host-registered named function (the chain carries no code)

arity 3 · slot 2=action / slot 3=parameter · dependencies: none · 1 actions (Common)

Shared input for this section:

```text
'hello'
```

### Actions (sorted by commonness)

#### `*` — registered: demo_upper
- tier ★★ Common · parameter slot: the value itself
- note: dynamic action space: slot 2 carries the host-registered function name
- chain: `[["udf", "demo_upper", ""]]`
- input: the shared sample above
- output: `Ok(value='HELLO')` (Ok)

### Invalid forms

| invalid chain | code | pointer | message | fix |
|---|---|---|---|---|
| `[["udf", "not_registered", ""]]` | `UP2-E1010` | `/0/1` | the custom function 'not_registered' is not registered | call register_udf(name, function) in the host, or declare an entry point (group uniparser2.udfs) |


## `each` — One dictionary per element of a list

arity 2 · slot 2=fields · dependencies: none · 1 actions (Core)

Shared input for this section:

```text
['  a  ', 'bb']
```

### Actions (sorted by commonness)

#### `each` — Run the field map once per element
- tier ★★★ Core · parameter slot: the value itself · `fields: fields`
- note: 2 positions: field map; one dictionary per element
- chain: `[["each", {"title": [["py", "strip", ""]], "size": [["py", "len", ""]]}]]`
- input: the shared sample above
- output: `Ok(value=[{'title': 'a', 'size': 5}, {'title': 'bb', 'size': 2}])` (Ok)


## Appendix: mechanisms shared by all operators

These are **not grouped by operator**: the tri-state and the parameter forms belong to every operator, so slicing them per operator would hide the differences.

### A. Tri-state

A missing value is not a value: it stays `Missing` and the key is absent from a product. A failed stage always fails the run with the code it reported.

#### `Ok (hit)` — tri-state
- tier ★★★ Core
- chain: `[["css1", "text", "h1.article-title"]]`
- input: `'\n<html>\n  <head>\n    <meta name="PubDate" content="2026-09-24 15:30:00">\n    <title>Notice on Issuing the Government Service Item List</title>\n  </head>\n  <body>\n    <h1 cl…`
- output: `Ok(value='  Notice on Issuing the Government Service Item List  ')` (Ok)

#### `Missing (no match: the value is not there)` — tri-state
- tier ★★★ Core
- note: a missing value is not a value: no empty string, no null
- chain: `[["css1", "text", "div.nope"]]`
- input: `'\n<html>\n  <head>\n    <meta name="PubDate" content="2026-09-24 15:30:00">\n    <title>Notice on Issuing the Government Service Item List</title>\n  </head>\n  <body>\n    <h1 cl…`
- output: `Missing(reason='no node matched')` (Missing)

#### `Failed (input type mismatch)` — tri-state
- tier ★★★ Core
- note: UP2-E2002
- chain: `[["py", "strip_tags", ""]]`
- input: `42`
- output: `Failed(code='UP2-E2002', reason='py.strip_tags needs a str, got int', fix='turn the upstream value into text with py.strip_tags / py.getitem first')` (Failed)

#### `Failed (evaluation failed)` — tri-state
- tier ★★★ Core
- note: UP2-E2005
- chain: `[["py", "int", ""]]`
- input: `'abc'`
- output: `Failed(code='UP2-E2005', reason="py.int conversion failed: invalid literal for int() with base 10: 'abc'", fix='check the shape of the source value first (py.default can serve as a…` (Failed)

#### `Failed (a subscript that is not there)` — tri-state
- tier ★★★ Core
- note: UP2-E2018: the dict is there, the key is not — an error, not a Missing value
- chain: `[["py", "getitem", "text"]]`
- input: `{'a': 1}`
- output: `Failed(code='UP2-E2018', reason="KeyError: 'text' — the dict has no key 'text'", fix='read a key the mapping has, or make the producing stage write it')` (Failed)

#### `Failed (an attribute that is a method)` — tri-state
- tier ★★★ Core
- note: UP2-E2002: py.getattr never calls a method (the fix names an operator or a udf)
- chain: `[["py", "getattr", "json"]]`
- input: `_HostObject(status=200, url='https://example.com/list.html')`
- output: `Failed(code='UP2-E2002', reason="the attribute 'json' of _HostObject is callable, and py.getattr never calls it", fix='a method is not a value: read the text with ["css","text",""]…` (Failed)

#### `Failed (an absent attribute)` — tri-state
- tier ★★★ Core
- note: UP2-E2002 whose reason begins with the exception class: AttributeError: ...
- chain: `[["py", "getattr", "txet"]]`
- input: `_HostObject(status=200, url='https://example.com/list.html')`
- output: `Failed(code='UP2-E2002', reason="AttributeError: '_HostObject' object has no attribute 'txet'", fix='check the attribute name against the value, or make the producing stage write i…` (Failed)

#### `Failed (sandbox code raised)` — tri-state
- tier ★★★ Core
- note: UP2-E2017 (the sandbox code can catch it with try/except)
- chain: `[["code", {"src": "1 / 0"}]]`
- input: `None`
- output: `Failed(code='UP2-E2017', reason='the sandboxed code raised an exception: ZeroDivisionError: division by zero', fix='fix src; the snippet can catch it itself with try/except')` (Failed)

#### `Failed (sandbox execution over limit)` — tri-state
- tier ★★★ Core
- note: UP2-E2016: limits are configured by the host (a tiny time budget is used here)
- chain: `[["code", {"src": "while True:\n    pass"}]]`
- input: `None`
- output: `Failed(code='UP2-E2016', reason='sandbox execution exceeded its limits: TimeoutError: feed time limit exceeded: <measured> fix='reduce the data volume or rewrite the algorithm; lim…` (Failed)

### B. Parameter forms

The scalar / positional array / named object / reference / directive forms of the parameter slot.

#### `scalar parameter` — form
- tier ★★★ Core
- chain: `[["py", "urljoin", "https://x/p/"]]`
- input: `'a.html'`
- output: `Ok(value='https://x/p/a.html')` (Ok)

#### `positional array` — form
- tier ★★★ Core
- chain: `[["py", "replace", ["old", "new"]]]`
- input: `'old text'`
- output: `Ok(value='new text')` (Ok)

#### `named object` — form
- tier ★★★ Core
- chain: `[["re", "group", {"pattern": "(\\d+)", "group": 1}]]`
- input: `'x42'`
- output: `Ok(value='42')` (Ok)

#### `reference ($globals / $locals)` — form
- tier ★★★ Core
- chain: `[["py", "urljoin", "$globals.base"]]`
- input: `'a'`
- output: `Ok(value='https://x/a')` (Ok)

#### `directive object {"$lit": …}: a literal starting with $` — form
- tier ★★★ Core
- note: without $lit it is a reference (E1006, see the invalid-form sections)
- chain: `[["py", "default", {"$lit": "$fields.title"}]]`
- input: `''`
- output: `Ok(value='$fields.title')` (Ok)

#### `css empty selector = the current node itself` — form
- tier ★★★ Core
- chain: `[["css1", "text", ""]]`
- input: `'<p>plain text supplied directly</p>'`
- output: `Ok(value='plain text supplied directly')` (Ok)

### C. Invalid forms owned by no operator

| invalid chain | code | pointer | message | fix |
|---|---|---|---|---|
| `[["nope", "strip", ""]]` | `UP2-E1001` | `/0/0` | unknown operator 'nope' | use one of the following operators |
