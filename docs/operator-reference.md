# Operator reference

The registry declares **10 operators and 77 `(operator, action)` pairs**; all of them are listed below.
The READMEs carry a one-screen summary of what the engine ships; this page is the reference next to
it: what each action means, which writing its parameter slot takes, and a set of chains whose outputs
were produced by running them.

It is **hand-maintained**. The authority is the registry, so ask it — `uv run up2 ops --json` is the
machine-readable list of every operator, action, parameter schema, dependency and availability, and
`uv run up2 ops` is the readable view. The design notes in [`specs/`](specs) are the specification;
this page is a map, not a second source of truth.

## How a stage is written

A stage is a JSON array. `css` / `css1` / `xpath` / `re` / `py` / `ctx` / `udf` declare more than one
action, so they write `[operator, action]` or `[operator, action, parameter]`; `json` / `code` / `each`
declare exactly one, so the action is never written and the stage is `[operator]` or
`[operator, parameter]`:

| Position | Holds |
|---|---|
| 1 | the operator name (`css` / `py` / …) |
| 2 | the action (or the accessor of the selector family) for a multi-action operator; the parameter for a single-action one |
| 3 | the parameter of a multi-action operator |

**The parameter slot is written in one of three ways**, decided by how many parameters the action still
has to fill (a parameter the action slot itself provides — `css`'s `@href` providing `attr` — does not
count):

| Form | When | Example |
|---|---|---|
| the value itself | exactly one parameter left | `["py", "slice", "0:4"]` |
| a positional array | two or more fixed parameters | `["py", "replace", ["old", "new"]]` |
| an object | a data map only: `each`'s field map, `ctx.dict`, `xpath`'s namespace map | `["ctx","dict",{"u":"obj","base":"globals.base"}]` |
| nothing | no required parameter left | `["py","strip"]`, `["json"]` |

An object is **never a parameter list**: a single-parameter action takes the value itself, so
`["py", "urljoin", {"base": "…"}]` is the object as `urljoin`'s value and is rejected at compile time
with `UP2-E1005` instead of silently doing something else. `{"$lit": …}` is the escape for a literal
that starts with `$`; a leading `$` in a `ref_or_literal` position is a reference
(`"$globals.base_url"`), and `$obj` names the whole value the stage received (`$in` names the story
step's input). The escape works at any depth, so `["py","or",[{"$lit":"$a"},"fallback"]]` quotes the
text inside an array as well; a `$`-prefixed single-key object anywhere in such a parameter is a
directive or an error, never data.

Every stage is validated **before the chain runs**: unknown operator or action, wrong arity, a
parameter that does not match the declared schema, a dangling reference, a cross-node reference to a
`_`-prefixed local, `ctx.set` outside `locals` / `public`, and a ReDoS-shaped regex all fail with a
`UP2-E*` code and a JSON Pointer. `uv run up2 lint <chain.json>` performs exactly that check.

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

The expression goes in the parameter slot, bare — `["xpath", "text", "//item/title"]` — or as a
two-element positional array when a namespace map is needed:
`["xpath", "text", ["//dc:creator", {"dc": "…"}]]`. XML goes through XPath rather than
CSS because `lxml` has no CSS selector without an extra package.

### `json` — jmespath (engine: jmespath, extra `[json]`)

A single action, `get`, whose parameter is a jmespath expression written in jmespath itself, with no
root sigil: `["json", "data.list[*].url"]`. Omitting the slot queries the whole document (`["json"]`).
It is a 2-position operator, so the action name is never written. A `$` prefix is the DSL's reference
sigil, not a JSONPath root, and `JSON.` is not a jmespath prefix.

### `re` — regular expressions (standard library)

| Action | Meaning |
|---|---|
| `search` | the whole first match, `group(0)`; `[pattern, group]` takes one capture group (an index or a name) |
| `findall` | every match (Python's `findall`; a tuple becomes an array) |
| `sub` | replace every match: `[pattern, replacement]`, with `\N` / `\g<name>` checked at compile time |

Regexes are pre-compiled at compile time, and a nested-quantifier shape is rejected there (ReDoS).
Python's `re` has **no** timeout parameter, so there is no runtime backstop — see `specs/002` §6.3.

### `py` — the allowlist of pure functions (standard library)

48 functions, JSON in and JSON out, no IO. A closed set: an unknown name is `UP2-E1003`. The predicate
actions use Python's own spellings, so a chain reads like the expression it means.

| Purpose | Functions |
|---|---|
| text | `const` · `strip` (optional `chars`) · `normalize_space` · `html_to_markdown` · `replace ["old","new"]` · `split` · `join` · `upper` · `lower` · `slice` · `len` |
| collections | `first` · `last` · `flatten` · `uniq` · `sort` · `sort_desc` · `find_jsons` · `getitem` · `filter` (keep truthy, or falsy with `false`) |
| host object | `getattr` — read an attribute of the value that flows in (a method is never called) |
| URL | `urljoin` · `urlsplit` |
| encoding / hash | `b64_encode` · `b64_decode` · `sha256` · `md5` (checksums and ETags only, never security) |
| conversion | `str` · `int` · `float` · `bool` · `from_json` |
| time | `strptime` (text + explicit format → `datetime`) · `strftime` (`datetime` → text) · `from_timestamp` / `to_timestamp` (epoch seconds ↔ `datetime`) · `sleep` (block N seconds, return the upstream value) |
| predicate | `==` · `!=` · `<` · `<=` · `>` · `>=` · `in` · `between` (one parameter each; `["py","==",200]`) |
| selection | `or` · `and` (Python's, over `[upstream, *operands]`: `["py","or",["$locals._a","fallback"]]`) |

`const` writes a literal verbatim and never resolves it as a reference: `["py","const","article"]`.

The comparisons follow Python: `==` / `!=` compare any two JSON values with Python's own equality — deep
equality for containers, no string coercion (`200` is not `"200"`), and `1` **is** equal to `true`
(`bool` is an `int`). The four orderings take a **comparable pair only** (two numbers or two strings), and
a boolean is not a number here, so `["py","<",2]` on `true` is `UP2-E2002` — the one place where the two
families disagree. A **bare `null`** is a literal when the action declares a required parameter
(`["py","==",null]` tests against `null`) and a "no parameter" placeholder only when nothing is required
(`["py","strip",null]` is `["py","strip"]`). A null test is also written `["py","in",[null]]`.

`in` keeps Python's operand order — the parameter is the container: `["py","in",[200,301,302]]` asks
whether the value is one of those, and "the URL contains `/public/`" puts the element in front:
`[["py","const","/public/"],["py","in","$locals.url"]]`.

`between` is the half-open numeric interval `lo <= value < hi`: `["py","between",[200,300]]` answers
`false` for `300`. It compares numbers only — no string ordering, no coercion — and a boolean is not a
number.

`or` / `and` answer with an **operand**, not a boolean (`or` over `["", 0]` answers `0`, which is
Python's answer), so they serve both selection and judgement. The **upstream value is the first
operand**, so `["py","or",[a,b]]` reads `value or a or b`, an empty operand array answers the upstream
value, and `or` is the fallback: `["py","or",[0]]` answers `0` when the value is empty. `$obj` lets a
saved candidate come before the live one: `["py","or",["$locals.meta_title","$obj"]]`. Their operands
have to **exist**: a path that cannot be read fails the whole stage before the action runs — every
operator's parameters behave that way — so "take A, else B" covers candidates that are present but
empty. To negate a boolean, compare it: `["py","!=",true]`; there is deliberately no `not` action.

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

**Identity is `[]`**: a chain whose value **is** its own input is the empty array. The whole-chain
reference (`"$in"`, `["$in", …]`) was retired with the step model (`03` §2.3); read a field with a
stage or a reference parameter.

The parameter slot is written bare for every single-parameter action (`const`, `strip`, `split`, `join`,
`urljoin`, `urlsplit`, `slice`, `getitem`, `getattr`, `strptime`, `strftime`, `from_timestamp`,
`to_timestamp`, `==`, `!=`, `<`, `<=`, `>`, `>=`, `in`, `between`, `or`, `and`), and as a two-element
positional array for `replace`: `["py","replace",["old","new"]]`. A container
where the function needs a scalar is a compile-time `UP2-E1005` (`urljoin.base`, `slice.spec`,
`split.sep`, `getitem.at`, `getattr.ref_or_literal`, `replace.old`, `replace.new`,
`strftime.layout`, `strptime.format`, and a `between` bound that is not a number).

`strptime` parses the upstream text with one explicit, literal format and answers a `datetime`; there is
no format guessing, and a text that does not match is `UP2-E2005` naming the format. `strftime` renders
a `datetime` back to text. A `datetime` may flow between stages, but it is not exportable: a chain that
ends with one fails at the exit with `UP2-E2003`, whose fix names `["py","strftime",…]`. The format is
validated at compile time against a locale-free allowlist, so `%B` / `%b` / `%a` / `%p` and `%Z` are
compile errors. `from_timestamp` / `to_timestamp` convert epoch seconds at a fixed offset (hours, a
half-hour zone writes `5.5`; default `0` = UTC), with no timezone database or DST.

### `ctx` — the scope (standard library)

| Action | Meaning |
|---|---|
| `get` | read a scope path |
| `set` | write the upstream value into `locals` or `public` |
| `del` | delete a path in `locals` or `public` |
| `dict` | collect several paths into an object (`name → path`) |
| `list` | collect several paths into a list (an array of paths) |

Paths are written bare, without `$` and without a `ctx.` prefix: `["ctx", "set", "locals.year"]` —
`"$locals.year"` is the reference spelling of another operator's parameter slot, and `ctx` reports it
with a fix line saying to drop the `$`.
The readable roots are `globals` / `locals` / `public` / `obj`; `obj` names the whole value the stage
received and takes no path, so reading a field is `["ctx","get","obj"]` followed by
`["py","getitem",…]`. `globals` is read-only and `locals` / `public` are writable; a write outside
`locals.*` or `public.*` is `UP2-E1015` at compile time. One polymorphic `map` used to answer two
different types depending on its parameter's shape; the two actions now say which shape they produce
(`ctx-dict-list-and-py-table`).

### The scopes

| Scope | Lifetime | Writable | What it is |
|---|---|---|---|
| `globals` | the chain | no | the chain's static constants (fingerprinted) |
| `public` | the run | yes (`ctx.set`) | the run's own notes — shared by every node, never fingerprinted |
| `locals` | the current field | yes (`ctx.set`) | the field's scratch space |

`$public.x` reads the shared scope, so a value written in one node is readable in the next. It is
**not** a writable `globals`: `globals` is covered by the fingerprint, so writing it would break
"same chain, same result". `obj` is not a scope at all: it is the value the stage received, read-only,
and it is the same value `$obj` names in a parameter.

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

### `each` — a field map or one chain per element of a list (standard library)

The single argument's **shape selects the mode**. An **object** is a **field map** — `field name →
chain`, the same shape a node's `fields` block has. The input must be a list, and the result is one
dictionary per element, in input order:

```jsonc
[["css", "nodes", "ul.rel li"],
 ["each", {"title": [["css1", "text", "a"]], "href": [["css1", "@href", "a"]]}]]
// -> [{"title": "Related one", "href": "/p/1.html"}, {"title": "Related two", "href": "/p/2.html"}]
```

An **array** is **one chain** run over every element; the result is one product per element, in input
order: `["each", [["py","strip"]]]` on `[" a ", " b "]` yields `["a","b"]`. Calling a registered host
function per element is this array form with a `udf` stage (`["each",["udf","normalize"]]`).

- Each field chain starts from the element, and the fields are evaluated in declaration order against
  one element at a time.
- A field name starting with `_` is a **temporary of that element**, not a key of its dictionary:
  `["each", {"_t": [["py","strip"]], "v": [["ctx","get","locals._t"]]}]` on `[" x "]` yields
  `[{"v": "x"}]`.
- Every element is evaluated in **its own scope**: a read falls back outward **by name** (the innermost
  scope holding the path's first segment resolves the whole path, so a name the element wrote is never
  read from the calling scope), writes stay in the element, and the element's locals do not outlive it.
- The input must be a list (otherwise `UP2-E2002`); an empty list yields `[]`; a list longer than
  `MAX_EACH_ITER` (10 000) fails with `UP2-E2012` before anything runs; nesting a field map deeper
  than `MAX_EACH_DEPTH` (3) is `UP2-E1012` at compile time, and so is a map holding more than
  `MAX_FIELDS_PER_MAP` (256) fields, while an empty map — or a field name that is empty or contains `.`
  — is `UP2-E1005`. An empty array is `UP2-E1004` (an empty chain), and a parameter that is neither an
  object nor an array is `UP2-E1005`, naming both accepted shapes.

### `udf` — host-registered functions (no extra)

The action **is** the function name. The third slot selects the call:

| Slot 3 | Call |
|---|---|
| omitted | `f(value)` — the upstream value is one DTO argument |
| `"*"` | `f(*value)` — the upstream value must be a list |
| `"**"` | `f(**value)` — the upstream value must be a mapping |
| anything else | `f(argument)` — one explicit argument |

The chain carries no code — only a name from the run's table (`register_udf`, or
`run(…, udfs={...})`); a missing name is `UP2-E1010`, reported by `run` before evaluation. A udf may
answer **any** value: a response object flows to the next stage and is read with `py.getattr`, while
the run's exit and a `["type", …]` stage still require JSON. An awaitable answer is `UP2-E2009`; the
kernel is synchronous.

### `node` — call a story node (no extra)

`["node", "detail"]` runs the node `detail` with the current value as its `$in` and answers that
node's product. The call shares the caller's `$locals`, and the caller's `$in` is restored afterwards.
The name is literal and must be a node of the same story (`UP2-E1016` otherwise); the node-call graph
is acyclic (`UP2-E1017`). A `node` stage has no argument slot: put a stage in front of it to produce
a different input. A standalone chain (compiled without a story) rejects the stage.

### `type` — validate a chain's product (no extra)

`["type", "Article"]` builds the host-registered type from the current value and answers the JSON the
constructor approved. A mapping is `Cls(**payload)`, a list `Cls(*items)`, anything else `Cls(value)`.
An unregistered name is `UP2-E1011`; a raising constructor is `UP2-E2019`; a non-JSON approval is
`UP2-E2003`. The stage must be the **last** stage of its chain (`UP2-E1005` otherwise). A field-map
node has no tail, so wrap it: `[["node","fields"], ["type","Article"]]`.

### `code` — code inside the chain (optional extra `[code]`)

The source is the parameter: `["code", "len(obj) * 2"]`. `obj` is the upstream value and `ctx` is the
scope's JSON projection, read attribute-style (`ctx.locals.n`, `ctx.globals.base_url`); `inputs` is
retired, because every other value is already reachable through `ctx`. `print` output is dropped. The
snippet runs in a **language-level sandbox**; the operator is absent from a default install and from
`uniparser2[all]`, and without the extra it fails at compile time with `UP2-E1107`. `UP2_CODE=off` refuses it at compile time with the same code. Host-configured limits
(64 MB, 0.5 s per evaluation by default) and a deterministic clock/sleep/random policy apply, and the
chain cannot loosen them. What the sandbox does and does not expose is listed surface by surface in
`specs/004` §11.3.

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
[["css1", "text", "h1.article-title"], ["py","normalize_space"]]
// → Ok('Notice on Issuing the Government Service Item List')

// a capture group, then a conversion
[["re", "search", ["(\\d{4})-(\\d{2})", 1]], ["py","int"]]
// → Ok(2026)                                    (input "published 2026-09")

// JSON text → a jmespath query (no root sigil) → the first element
[["json", "data.list[*].url"], ["py","first"]]
// → Ok('https://x/1')

// XML: every <loc>, then the last one
[["xpath", "text", "//*[local-name()='loc']"], ["py","last"]]
// → Ok('https://x/2')

// XML with a namespace prefix (expression and namespace map as one positional array)
[["xpath", "text", ["//dc:creator", {"dc": "http://purl.org/dc/elements/1.1/"}]]]
// → Ok(['Jane Reporter'])

// a machine timestamp → a datetime → another layout
[["py", "strptime", "%Y-%m-%dT%H:%M:%S%z"], ["py", "strftime", "%Y/%m/%d"]]
// → Ok('2026/09/24')                            (input "2026-09-24T15:30:00+0800")

// epoch seconds → an aware datetime at a fixed offset → text
[["py", "from_timestamp", 8], ["py", "strftime", "%Y-%m-%d %H:%M:%S"]]
// → Ok('1970-01-01 08:00:00')                   (input 0)

// the upstream value is `or`'s first operand, so this is the fallback
[["py", "or", [0]]]
// → Ok(0)                                       (input "")

// a scope round trip
[["ctx", "set", "locals.n"], ["ctx", "get", "locals.n"]]
// → Ok('77')

// the sandbox (needs uniparser2[code])
[["code", "len(obj) * 2"]]
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
