# Operator reference

The registry declares **11 operators and 72 `(operator, action)` pairs**; all of them are listed below.
The READMEs carry a one-screen summary of what the engine ships; this page is the reference next to
it: what each action means, which writing its parameter slot takes, and a set of chains whose outputs
were produced by running them.

It is **hand-maintained**. The authority is the registry, so ask it — `uv run up2 ops --json` is the
machine-readable list of every operator, action, parameter schema, dependency and availability, and
`uv run up2 ops` is the readable view. The design notes in [`specs/`](specs) are the specification;
this page is a map, not a second source of truth.

## How a stage is written

A stage is a JSON array. Three positions for `css` / `css1` / `xpath` / `re` / `py` / `ctx` / `udf`,
two for `json` / `const` / `code` / `each` (which carry no separate action):

| Position | Holds |
|---|---|
| 1 | the operator name (`css` / `py` / …) |
| 2 | the action, or the accessor of the selector family (`text` / `@href` / `nodes`) |
| 3 | the parameter — for a 2-position operator it is position 2 |

**The parameter slot is written in one of three ways**, decided by how many parameters the action still
has to fill (a parameter the action slot itself provides — `css`'s `@href` providing `attr` — does not
count):

| Form | When | Example |
|---|---|---|
| the value itself | exactly one parameter left | `["py", "slice", "0:4"]` |
| a named object (a positional array is equally accepted) | two or more left | `["re", "group", {"pattern": "…", "group": 1}]` |
| nothing | no parameter | `["py", "strip", ""]`, or drop the third position |

A named object is **not** a binding for a single-parameter action: there it is the parameter's value,
so `["py", "urljoin", {"base": "…"}]` is rejected at compile time with `UP2-E1005` instead of silently
doing something else. `{"$lit": …}` is the escape for a literal that starts with `$`; a leading `$` in
a `ref_or_literal` position is a reference (`"$globals.base_url"`).

Every stage is validated **before the chain runs**: unknown operator or action, wrong arity, a
parameter that does not match the declared schema, a dangling reference, a cross-node reference to a
`_`-prefixed local, `ctx.set` outside `locals`, and a ReDoS-shaped regex all fail with a `UP2-E*` code
and a JSON Pointer. `uv run up2 lint <chain.json>` performs exactly that check.

## The operators

### `css` / `css1` — CSS selectors (engine: selectolax, extra `[html]`)

| Accessor | Meaning |
|---|---|
| `text` | plain text (without `<script>` / `<style>` / `<noscript>`) |
| `html` | inner HTML |
| `outer` | outer HTML |
| `@<attribute>` | an attribute value, e.g. `["css1", "@href", "a.download"]` |
| `remove` | a copy of the node with the matching nodes pruned |
| `self` | the node handle itself (for a later stage) |
| `nodes` | the set of matching nodes |
| `exists` | `true` / `false`: does the selector match at least one node |

`css` yields **every** match (a list), `css1` only the first (a scalar) — the cardinality is explicit
rather than a switch, because a silent truncation is worse than a longer name. An empty selector means
"the node itself".

Use `exists` when the chain only needs a decision: `["css","nodes",S]` answers `[]` when nothing
matches (an empty value, `01` §4.2), while `["css","exists",S]` answers `false`.

### `xpath` — XPath on XML (engine: lxml, extra `[xml]`)

| Accessor | Meaning |
|---|---|
| `text` | text value (elements: all descendant text; attributes as-is) |
| `self` | the first matching node (relative paths can keep selecting from it) |
| `nodes` | the set of matching nodes |

The expression goes in the parameter slot, bare — `["xpath", "text", "//item/title"]` — or as an object
when a namespace map is needed:
`["xpath", "text", {"expr": "//dc:creator", "ns": {"dc": "…"}}]`. XML goes through XPath rather than
CSS because `lxml` has no CSS selector without an extra package.

### `json` — jmespath (engine: jmespath, extra `[json]`)

A single action, `get`, whose parameter is a jmespath expression; an empty expression means the root:
`["json", "data.list[*].url"]`. It is a 2-position operator, so the action name is never written.

### `re` — regular expressions (standard library)

| Action | Meaning |
|---|---|
| `search` | the whole first match, `group(0)` |
| `group` | one capture group, named: `{"pattern": "…", "group": 1}` |
| `findall` | every match |

Regexes are pre-compiled at compile time, and a nested-quantifier shape is rejected there (ReDoS).
Python's `re` has **no** timeout parameter, so there is no runtime backstop — see `specs/002` §6.3.

### `py` — the allowlist of pure functions (standard library)

42 functions, JSON in and JSON out, no IO. A closed set: an unknown name is `UP2-E1003`. The predicate
actions use Python's own spellings, so a chain reads like the expression it means.

| Purpose | Functions |
|---|---|
| text | `strip` · `strip_tags` · `normalize_space` · `upper` · `lower` · `replace {"old","new"}` · `split {"sep","maxsplit"?}` · `join` · `slice` · `len` |
| collections | `first` · `last` · `flatten` · `uniq` · `sort {"key"?,"reverse"?}` · `getitem` |
| host object | `getattr` — read an attribute of the value that flows in (a method is never called) |
| URL | `urljoin` · `urlsplit` |
| encoding / hash | `b64_encode` · `b64_decode` · `sha256` |
| conversion | `str` · `int` · `float` · `bool` · `list` · `from_json` |
| predicate | `==` · `!=` · `<` · `<=` · `>` · `>=` · `in` (one parameter each; `["py","==",200]`) |
| selection | `or` · `and` (Python's, over an **array** of already-computed operands: `["py","or",["$locals._a","fallback"]]`) |
| fallback | `default` — replaces `None` or an empty string in one field; its value may be any JSON value, a container included |
| time (input) | `parse_time` — a time string → the canonical `%Y-%m-%d %H:%M:%S`, in the order **explicit `format`** → **built-in table** (no dependency) → **natural-language detection** (`[time]`); `lang` restricts the detection, `date_order` (`MDY`/`DMY`/`YMD`, default `DMY`) decides an ambiguous slash writing, `now` (e.g. `"$globals.now"`) pins the base clock of a relative expression |
| time (output) | `strftime` — the canonical string → another layout (`%Y/%m/%d`), allowlisted to directives that no locale or platform decides |
| formats | `html_to_markdown` (`[md]`) |

The comparisons follow Python: `==` / `!=` compare any two JSON values with Python's own equality — deep
equality for containers, no string coercion (`200` is not `"200"`), and `1` **is** equal to `true`
(`bool` is an `int`). The four orderings take a **comparable pair only** (two numbers or two strings), and
a boolean is not a number here, so `["py","<",2]` on `true` is `UP2-E2002` — the one place where the two
families disagree. A **bare `null`** cannot be written as the parameter at all: `["py","==",null]` is
`UP2-E1005` ("missing required parameter"), because the machinery cannot tell a written `null` from an
omitted one — true of every scalar parameter in the DSL, not just these actions. A null test is written
`["py","in",[null]]`.

`in` keeps Python's operand order — the parameter is the container: `["py","in",[200,301,302]]` asks
whether the value is one of those, and "the URL contains `/public/`" puts the element in front:
`[["const","/public/"],["py","in","$locals.url"]]`.

`or` / `and` answer with an **operand**, not a boolean (`or` over `["", 0]` answers `0`, which is
Python's answer), so they serve both selection and judgement. Their operands have to **exist**: a path
that cannot be read fails the whole stage before the action runs — every operator's parameters behave that
way — so "take A, else B" covers candidates that are present but empty, and one that may be empty is
defaulted first (`[["css1","text","h1"],["py","default",""]]`). To negate a boolean, compare it:
`["py","!=",true]`; there is deliberately no `not` action.

`getitem` is the **only subscript action** (Python's `__getitem__`): a sequence by integer index, a
mapping by string key, a str by character, and **no coercion** — `["py","getitem","0"]` on a list is
`UP2-E2002`, never index `0`. A key or an index the value does not have is `UP2-E2018` (the value is
there, the subscript is not — `KeyError: 'text' — the dict has no key 'text'`), never an empty value. Its
parameter is a literal or a reference, so `["py","getitem","$globals.key"]` reads a computed key.

`getattr` is its twin for a **host object**: it reads the value's own attribute
(`["py","getattr","status_code"]` on a response, `["py","getattr","attributes"]` on a `selectolax`
node), which is what a value that is not JSON needs. An absent attribute is `UP2-E2002` and its `reason`
begins with the exception's own class — `AttributeError: 'Response' object has no attribute 'txet'` — and
An attribute that is **callable** is refused with the same code: a method is never called (a
zero-argument method such as `selectolax`'s `decompose` mutates the tree), so the `fix` names the operator
to use instead (`["css","text",""]`) or a `udf`. A value with no attributes at all (an integer, say) is
the same `AttributeError` failure.

**Identity is not an action**: where a step's value **is** its own input, the chain is the reference
`"$in"` (or `["$in", …]` to read a field of it first). `py.id` was retired with the identity stages
(`03` §2, §12.6 E4).

The parameter slot is written bare for `urljoin` / `slice` / `getitem` / `getattr` / `join` / `urlsplit` /
`default` / `strftime` / `==` / `!=` / `<` / `<=` / `>` / `>=` / `in` / `or` / `and`, and as a named
object for `split` / `replace` / `sort` / `parse_time`. A container
where the function needs a scalar is a compile-time `UP2-E1005` (`urljoin.base`, `slice.spec`,
`split.sep`, `split.maxsplit`, `getitem.at`, `getattr.ref_or_literal`, `replace.old`, `replace.new`,
`strftime.layout`, and an unknown `sort.key`).

`parse_time` reaches the optional engine only after the built-in table has failed, so a machine shape
never loads it; without `uniparser2[time]` that path reports `UP2-E2008` and names the extra, while a
table shape keeps working. An explicit `format` and a `lang` are alternatives (`UP2-E1005` together),
because the format wins and the language could never take effect.

### `ctx` — the scope (standard library)

| Action | Meaning |
|---|---|
| `get` | read a scope path |
| `set` | write the upstream value into `locals` or `public` |
| `del` | delete a path in `locals` or `public` |
| `dict` | collect several paths into an object (`name → path`) |
| `list` | collect several paths into a list (an array of paths) |

Paths are written bare, without `$` and without a `ctx.` prefix: `["ctx", "set", "locals.year"]`.
`globals` is read-only and `locals` is local to the current evaluation; a write outside `locals.*` or
`public.*` is `UP2-E1015` at compile time. One polymorphic `map` used to answer two different types
depending on its parameter's shape; the two actions now say which shape they produce
(`ctx-dict-list-and-py-table`).

### The scopes

| Scope | Lifetime | Writable | What it is |
|---|---|---|---|
| `globals` | the chain | no | the chain's static constants (fingerprinted) |
| `public` | the run | yes (`ctx.set`) | the run's own notes — shared by every node, never fingerprinted |
| `locals` | the current field | yes (`ctx.set`) | the field's scratch space |

`$public.x` reads the shared scope, so a value written in one node is readable in the next. It is
**not** a writable `globals`: `globals` is covered by the fingerprint, so writing it would break
"same chain, same result".

### `try` — a guard directive, not an operator

`["try","skip"]` / `["try","break"]` / `["try","raise"]` protects **the stage immediately after it**:

| Policy | When the guarded stage fails |
|---|---|
| `raise` | the run fails (the default — the same as not writing it) |
| `skip` | the chain keeps the value it carried into that stage and carries on |
| `break` | the chain ends there, answering with the value it carried |

A guarded stage that **succeeds** disarms the guard, so a `try` never swallows a later failure. Two
`try` stages in a row, or a `try` at the end of a chain, are compile errors (`UP2-E1005`): a guard that
protects nothing is a mistake. The directive never turns an exception into a value — `skip` and `break`
keep a value the chain already had.

### `const` — a literal (standard library)

`["const", "article"]` produces its value verbatim, never resolving a reference. It is the building
block for constants inside a field chain.

### `each` — one dictionary per element of a list (standard library)

The single argument is a **field map**: an object of `field name → chain`, the same shape a node's
`fields` block has. The input must be a list, and the result is one dictionary per element, in input
order:

```jsonc
[["css", "nodes", "ul.rel li"],
 ["each", {"title": [["css1", "text", "a"]], "href": [["css1", "@href", "a"]]}]]
// -> [{"title": "Related one", "href": "/p/1.html"}, {"title": "Related two", "href": "/p/2.html"}]
```

- Each field chain starts from the element, and the fields are evaluated in declaration order against
  one element at a time.
- A field name starting with `_` is a **temporary of that element**, not a key of its dictionary:
  `["each", {"_t": [["py","strip",""]], "v": [["ctx","get","locals._t"]]}]` on `[" x "]` yields
  `[{"v": "x"}]`.
- Every element is evaluated in **its own scope**: a read falls back outward **by name** (the innermost
  scope holding the path's first segment resolves the whole path, so a name the element wrote is never
  read from the calling scope), writes stay in the element, and the element's locals do not outlive it.
- The input must be a list (otherwise `UP2-E2002`); an empty list yields `[]`; a list longer than
  `MAX_EACH_ITER` (10 000) fails with `UP2-E2012` before anything runs; nesting the field map deeper
  than `MAX_EACH_DEPTH` (3) is `UP2-E1012` at compile time, and so is a map holding more than
  `MAX_FIELDS_PER_MAP` (256) fields, while an empty map — or a field name that is empty or contains `.`
  — is `UP2-E1005`.

### `udf` — host-registered functions (no extra)

The action **is** the function name, and the parameter object is that function's keyword arguments:
`["udf", "my_clean", {"strict": true}]`. The chain carries no code — only a name the host registered
with `register_udf` (or an entry point in the group `uniparser2.udfs`); an unregistered name is
`UP2-E1010` at compile time. A function may declare a `ctx` parameter to receive the scope; `ctx` is
reserved and cannot be passed from the chain.

### `code` — code inside the chain (optional extra `[code]`)

One action, `run`: `["code", {"src": "len(obj) * 2", "inputs": {"x": "$locals.n"}}]`, where `obj` is the
upstream value and `inputs` is optional. The snippet runs in a **language-level sandbox**; the operator
is absent from a default install and from `uniparser2[all]`, and without the extra it fails at compile
time with `UP2-E1107`. Host-configured limits (64 MB, 0.5 s per evaluation by default) and a
deterministic clock/sleep/random policy apply, and the chain cannot loosen them. What the sandbox does
and does not expose is listed surface by surface in `specs/004` §11.3.

The sandbox mounts the `py` allowlist **by name**, so the predicate actions are mounted too — but a
snippet cannot call them by bare name: `in`, `or` and `and` are Python keywords and `==`, `!=`, `<`, `<=`,
`>`, `>=` are not identifiers. Inside `code`, write the language's own operators (`a == b`, `x in y`,
`a or b`) instead; the named form matters for chains, where the action name is data.

## Worked examples

Each line below is a real run; the input is named in the note.

```jsonc
// an attribute, resolved against the page base (scope: base_url = https://example.gov.cn/p/)
[["css1", "@href", "a.download"], ["py", "urljoin", "$globals.base_url"]]
// → Ok('https://example.gov.cn/files/list.pdf')

// plain text, whitespace collapsed
[["css1", "text", "h1.article-title"], ["py", "normalize_space", ""]]
// → Ok('Notice on Issuing the Government Service Item List')

// a capture group, then a conversion
[["re", "group", {"pattern": "(\\d{4})-(\\d{2})", "group": 1}], ["py", "int", ""]]
// → Ok(2026)                                    (input "published 2026-09")

// JSON text → a jmespath query → the first element
[["json", "data.list[*].url"], ["py", "first", ""]]
// → Ok('https://x/1')

// XML: every <loc>, then the last one
[["xpath", "text", "//*[local-name()='loc']"], ["py", "last", ""]]
// → Ok('https://x/2')

// XML with a namespace prefix (the expression as an object)
[["xpath", "text", {"expr": "//dc:creator", "ns": {"dc": "http://purl.org/dc/elements/1.1/"}}]]
// → Ok(['Jane Reporter'])

// a feed timestamp → the canonical shape → another layout (the output side)
[["py", "parse_time", ""], ["py", "strftime", "%Y/%m/%d"]]
// → Ok('2026/09/24')                            (input "Thu, 24 Sep 2026 15:30:00 +0800")

// no format and no language: the engine detects it (needs uniparser2[time])
[["py", "parse_time", ""]]
// → Ok('2026-09-24 00:00:00')                   (input "24. September 2026")

// a relative expression with a pinned base clock (scope: now = 2026-01-01 12:00:00)
[["py", "parse_time", {"now": "$globals.now"}]]
// → Ok('2026-01-02 12:00:00')                   (input "tomorrow")

// a scope round trip
[["ctx", "set", "locals.n"], ["ctx", "get", "locals.n"]]
// → Ok('77')

// the sandbox (needs uniparser2[code])
[["code", {"src": "len(obj) * 2"}]]
// → Ok(12)                                      (input "abcdef")
```

## Checking a chain

| Command | What it does |
|---|---|
| `uv run up2 ops --json` | the operator/action/parameter facts — read this before writing a chain |
| `uv run up2 lint chain.json` | compile-time validation, without executing |
| `uv run up2 trial chain.json --input 'text=…' --json` | run it on local inputs; `--global`, `--product` |
| `uv run up2 conformance --check` | the audit behind this project: every declared `(operator, action)` has a case, every implemented error code is asserted |
| `uv run up2 snapshot chain.json --domain D --key K --case C --accept` | freeze a case's product as its expected product |
| `uv run up2 test D K` | regress a stored chain over its samples; a story that fetches replays the **request cache** (`.cache/requests/`), and the CLI never reaches the network |

`tools/demo_report.py` renders the same kind of catalogue as an HTML page for local browsing
(`.cache/report/up2-report.html`): every declared pair, grouped by operator, with a real run per case,
the multi-stage compositions and the compile-time invalid forms.

## Fetching a page

The kernel never fetches anything: a story that produces a `Request` suspends the run, and the **host**
answers. The package offers a default for that side:

```python
from uniparser2.net import RequestCache, fetch

answer = fetch({"url": "https://example.com/page", "method": "GET"})   # → Response(text=…, url=…)
```

The request is the kernel's own `Request` product: `url` (required), `method`, `headers`, `timeout`,
`params`, and a body that is **base64 text** (`body`) or a JSON value (`json`) — a body is binary and
the request dictionary is JSON throughout.

`RequestCache` keeps the answers under `.cache/requests/` (never committed), keyed by the whole
request, so a second run replays them instead of the network:

```python
cache = RequestCache()
answer = cache.get(request) or fetch(request)   # a miss is a miss
cache.put(request, answer)
```
