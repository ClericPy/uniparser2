# Operator reference

The registry declares **11 operators and 61 `(operator, action)` pairs**; all of them are listed below.
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
| `exists` | `true` / `false`: does the selector match at least one node (**never** `Missing`) |

`css` yields **every** match (a list), `css1` only the first (a scalar) — the cardinality is explicit
rather than a switch, because a silent truncation is worse than a longer name. An empty selector means
"the node itself".

Use `exists` rather than `nodes` when the chain only needs to branch: `["css","nodes",S]` reports
`Missing` when nothing matches, so the missing-value policy decides the answer (`""` under the default,
`Missing` under `drop`, a failure under `raise`), while `["css","exists",S]` answers `false` under all
of them.

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

41 functions, JSON in and JSON out, no IO. A closed set: an unknown name is `UP2-E1003`. The predicate
actions use Python's own spellings, so a chain reads like the expression it means.

| Purpose | Functions |
|---|---|
| text | `strip` · `strip_tags` · `normalize_space` · `upper` · `lower` · `replace {"old","new"}` · `split {"sep","maxsplit"?}` · `join` · `slice` · `len` |
| collections | `first` · `last` · `flatten` · `uniq` · `sort {"key"?,"reverse"?}` · `getitem` · `get` |
| URL | `urljoin` · `urlsplit` |
| encoding / hash | `b64_encode` · `b64_decode` · `sha256` |
| conversion | `str` · `int` · `float` · `bool` · `list` · `from_json` |
| predicate | `==` · `!=` · `<` · `<=` · `>` · `>=` · `in` (one parameter each; `["py","==",200]`) |
| selection | `or` · `and` (Python's, over an **array** of already-computed operands: `["py","or",["$locals._a","fallback"]]`) |
| fallback | `default` — the only action that can swallow `Missing`; its value may be any JSON value, a container included |
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
Python's answer), so they serve both selection and judgement. Their operands have to **exist**: a missing
reference short-circuits the whole stage before the action runs — every operator's parameters behave that
way — so "take A, else B" covers candidates that are present but empty, and one that may be absent is made
present first (`[["css1","text","h1"],["py","default",""]]`). To negate a boolean, compare it:
`["py","!=",true]`; there is deliberately no `not` action.

The parameter slot is written bare for `urljoin` / `slice` / `getitem` / `get` / `join` / `urlsplit` /
`default` / `strftime` / `==` / `!=` / `<` / `<=` / `>` / `>=` / `in` / `or` / `and`, and as a named
object for `split` / `replace` / `sort` / `parse_time`. A container
where the function needs a scalar is a compile-time `UP2-E1005` (`urljoin.base`, `slice.spec`,
`split.sep`, `split.maxsplit`, `getitem.index`, `get.key`, `replace.old`, `replace.new`,
`strftime.layout`, and an unknown `sort.key`).

`parse_time` reaches the optional engine only after the built-in table has failed, so a machine shape
never loads it; without `uniparser2[time]` that path reports `UP2-E2008` and names the extra, while a
table shape keeps working. An explicit `format` and a `lang` are alternatives (`UP2-E1005` together),
because the format wins and the language could never take effect.

### `ctx` — the scope (standard library)

| Action | Meaning |
|---|---|
| `get` | read a scope path |
| `set` | write the upstream value into `locals` |
| `del` | delete a path in `locals` |
| `map` | collect several paths into a list or a dict |

Paths are written bare, without `$` and without a `ctx.` prefix: `["ctx", "set", "locals.year"]`.
`globals` is read-only and `locals` is local to the current evaluation; a write outside `locals.*` is
`UP2-E1015` at compile time.

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
| `uv run up2 trial chain.json --input 'text=…' --json` | run it on local inputs; `--global`, `--product`, `--on-missing`, `--on-error` |
| `uv run up2 conformance --check` | the audit behind this project: every declared `(operator, action)` has a case, every implemented error code is asserted |

`tools/demo_report.py` renders the same kind of catalogue as an HTML page for local browsing
(`.cache/report/up2-report.html`): every declared pair, grouped by operator, with a real run per case,
the multi-stage compositions and the compile-time invalid forms.
