# Design

## Context

The current grammar is in `02` §1/§4 and implemented by `core/ast.py` (stage shape) and
`core/compile.py` (`_classify` / `_build_params`). The measured shape distribution over the 108 stages
of the generated catalogue is: scalar 58, `""` placeholder 34, 2-slot 8, array 5, object 3 (one of
which — `ctx.dict` — is a data map). The everyday surface is therefore 0/1 parameters wide; the
objects and placeholders are the outliers.

## Goals / Non-Goals

**Goals**

- One rule for what slot 2 means, one rule for when slot 3 exists, one rule for parameter shapes.
- The common case written with nothing redundant.
- Every illegal form still fails at compile time with a code and a JSON Pointer.

**Non-Goals**

- Renaming operators or merging `css`/`css1`.
- Changing the value domain, references, `try`, or the story layer.
- A compact human notation (`re @…`): if it is wanted later, it belongs to a host-side preprocessor
  that lowers to the canonical chain, not to the stored format.

## Decisions

### D0 — `const` becomes `py.const` (decided 2026-11-08)

The `const` operator is removed; a native JSON-able constant is written `["py","const", x]`. The `py`
action table grows to 43, the operator count drops to 10, and the catalogue's `const` section merges
into `py`. The action ignores the upstream value (like `or`/`and`), its parameter is a literal (so a
string starting with `$` needs no escape), and the value must be a JSON value: a non-JSON one (a set,
an `Opaque` handle, bytes) is a compile error, not an export-time one.

**`null` needs no escape.** The reason `{"$lit": null}` existed is that `null` meant "no parameter".
The rule changes to: `null` is a placeholder only when the action declares **no required** parameter,
so `["py","const",null]` is the literal `null` while `["py","strip",null]` stays "no parameter".
`{"$lit": …}` remains for one case only: text starting with `$` in a `ref_or_literal` slot
(`["py","default",{"$lit":"$100"}]`).

### D1 — Slot 2

Slot 2 is the **action** when the operator declares more than one action (`css`, `css1`, `xpath`, `re`,
`ctx`, `py`, `udf`); it is the **parameter** when the operator declares exactly one (`json`, `each`,
`code`). This is the smallest rule that keeps a single-action stage short (a fake `value` action was
rejected as redundant) while removing every other ambiguity.

Alternative rejected: always write the action (`["const","value",x]`) — uniform but adds a word that
means nothing. Alternative rejected: dotted operator names (`["css.text","h1"]`) — a larger break with
no additional benefit.

### D2 — Slot 3 exists exactly when the action has parameters

A stage is `[operator]`, `[operator, action]` or `[operator, action, parameter]` (and
`[operator, parameter]` for a single-action operator). A trailing slot is omitted when the action has
no parameters, or when all its parameters are optional and the author wants the defaults:

```text
["py","strip"]            # 21 parameter-less functions
["py","to_timestamp"]     # tz is optional: the default is UTC
["json"]                  # whole document
["json","data.list[*].url"]
["py","const","article"]  # required parameter, always present
```

The `""` placeholder disappears from the grammar; a third slot that is empty is an error, not a
"no parameter" marker.

### D3 — Parameter shapes

One parameter is a value. Two or more fixed parameters are a **positional array** whose length is the
action's declared arity (`["py","replace",["old","new"]]`, `["re","search",[pattern, group]]`). An
array that is itself a value stays a value (`["py","in",[200,301]]`): the action's declaration decides
which one it is, never the shape. An object is reserved for a **data map** — `each`'s field map,
`ctx.dict`, `xpath`'s namespace map — so a missing or unknown fixed parameter points at `/0/2/<index>`.

### D4 — `re` gains `sub`, and no sigil

> Superseded by **D12** on two points: `group` merges into `search`, and a two-parameter action takes a
> two-element array (D3), not a named object. The `@` sigil rejection below still stands.

```
["re","search","\\d{4}-\\d{2}-\\d{2}"]
["re","findall","\\d+"]
["re","group",{"pattern":"(\\d{4})-(\\d{2})","group":2}]
["re","sub",{"pattern":"(\\d{4})-(\\d{2})-(\\d{2})","replace":"\\3/\\2/\\1"}]
```

`sub` replaces every match. Every `\N` / `\g<name>` in `replace` is checked against the pattern's
group count at compile time (`UP2-E1005` at `/0/2/replace`), the same way `re.group` checks its index.
An `@template` action sigil was considered and rejected: it would give `@` a second meaning (it is the
attribute sigil in `css`) for no capability that the action name does not already carry.

### D5 — Trim the parameters that leak a host API

| Action | Now | Target |
|---|---|---|
| `py.split` | `sep` + optional `maxsplit` | `sep` only; truncate with `slice`/`first` |
| `py.sort` | `{"key": "int", "reverse": true}` | `sort` / `sort_desc`, **no parameters**: `sorted(value)` and `sorted(value, reverse=True)` |
| `py.parse_time` | `lang` / `format` / `date_order` / `now` | **deleted**; `strptime` takes one literal `format` |
| `py.replace` | object or positional array | two-element array `["old","new"]` |

`parse_time` is removed rather than trimmed (D14): its four parameters were one symptom, but the
action's real job — guessing a format and detecting relative expressions — is what made it
non-deterministic and pulled in `dateparser`. `strptime` with an explicit format has none of that, and
relative/natural-language dates go to a host `udf`.

### D6 — `udf` parameters are validated at compile time

The function is registered before the chain compiles, so its signature is known. A non-object
parameter, an unknown keyword, or a missing required keyword must fail at compile time; today the first
surfaces at runtime as `UP2-E2002` and the second as `UP2-E2099`.

### D7 — `json` stays a single-action operator (decided 2026-11-08)

JMESPath is an expression language: filters, projections, pipes, slices and its function library all
live inside the expression, so one action covers them (`items[?price > \`15\`].name`,
`sort_by(items, &price)[*].name`, `length(items)`, `merge(meta, {m: \`1\`})`). The registry keeps the
action name `get` for the conformance audit and the report; the chain does not write it — that is the
single-action rule of D1/D2, not a missing action.

The expression is written in **jmespath itself, with no root sigil**. A JSONPath-style `$` and a
browser extension's `JSON.` prefix are both foreign here: `$` is the DSL's reference sigil, and
`JSON.data` would ask jmespath for a field literally named `JSON`. The document is implicit — a bare
path (`data.list[*].url`) starts at its root, and `["json"]` (no third slot) answers the document
whole. `["json","@"]` still compiles, because `@` is an ordinary jmespath token (`@.data`,
`length(@)` are its useful forms) and special-casing a lone `@` into an error would be an arbitrary
restriction on the expression language; it is simply never documented, since omitting the slot already
means the whole document.

A `del` action is rejected: JMESPath has no mutation, so deletion would add a second path language to
the operator, and the parsed tree is cached read-only for the run (`_parsed`), so a mutation would
either poison the cache or force a copy per call. Folding `json` into `py` is rejected too: the
operator set follows the data type / engine (`py` values, `json` JSON, `css` HTML, `xpath` XML, `re`
text), and moving JSON queries under `py` would break that grouping while HTML queries stayed under
`css`.

### D8 — `each` selects its mode by the parameter's shape (decided 2026-11-08)

`each` keeps two slots and gains no action slot. Its parameter is either:

- an **object** — a field map; every element produces one object (`[{"t":"a","n":3}, …]`);
- an **array** — one chain; every element produces one value (`["a","b"]`), which is the map form that
  is missing today (`["each",[["py","strip"]]]` currently fails with `UP2-E1005`).

Calling a registered function per element is the array form with a `udf` stage
(`["each",["udf","normalize"]]`), so no dedicated `call` action is needed and the ordinary compile-time
checks apply (`UP2-E1010` for an unregistered name). The two modes are unambiguous at compile time
(dict vs array); anything else is `UP2-E1005` naming both shapes, and an empty array is `UP2-E1004`
(empty chain). An action slot is deferred until a third mode appears that the shape cannot express
(a `filter`/`take`-style mode).

### D9 — `code` takes the source as its only parameter (decided 2026-11-08)

`code` stays a single-action operator with two slots, and its parameter is the source text itself:
`["code","normalize_space(obj)"]`. The `inputs` object is removed: `obj` is the upstream value, and
every other value is already reachable as `ctx.locals.*` / `ctx.globals.*` / `ctx.public.*`, so
`inputs` only renamed an existing read. The trade is recorded: an `inputs` reference was resolved at
compile time (`UP2-E1006` for an unknown root), while `ctx.locals.x` is a runtime attribute read
(`UP2-E2017` when the key is missing).

The sandbox is a separate Monty process with a restricted standard library; file, environment,
network and process operations are refused (`open`/`listdir`/`environ` denied, `socket`/`subprocess`
absent), values enter and leave as JSON, `ctx` is a JSON projection, the mounted `py` functions are
pure, and the clock and random seed are frozen. `import` is Monty's own module table, not the host
importer: `os` is a stub (`getcwd()` is `/`, `environ` raises, `path` is absent) and
`builtins`/`importlib`/`pickle`/`ctypes`/`glob`/`shutil` do not exist; `__builtins__`,
`__class__`/`__subclasses__` and a mounted function's `__globals__` are unreachable, so the classic
escape routes do not resolve. The limits are host-side and a chain cannot change
them (64 MB, 0.5 s feed, 5 s request timeout, 1000 round trips); an infinite loop and a 1 GB
allocation both trip `UP2-E2016`. The isolation guarantee is Monty's, which is why `code` stays an
opt-in extra outside `all` and no host object is ever mounted.

The built-ins are exactly two: `obj` (the upstream value, which must be JSON — an `Opaque` handle is
refused with `UP2-E2003`) and `ctx` (the scope's JSON projection, attribute-style:
`ctx.locals.k`; it is not subscriptable, and non-JSON scope values are dropped). `print` is silenced
by passing a discarding `print_callback` to `feed_run` — Monty defaults it to the host's stdout, and
shadowing the name in the prelude would only cover that spelling while `sys.stdout` has no `write`
anyway. A host-side gate `UP2_CODE=off` (and `configure(enabled=False)`) refuses the operator at
compile time with `UP2-E1107`; the default stays "available when the extra is installed", because the
extra is already the opt-in and `core` cannot read the environment to report otherwise.

### D10 — `udf` is a 2-slot unary call (decided 2026-11-08)

The operator has no third slot: `["udf","f"]`. The registered function receives the upstream value as
its only positional argument, and a function that takes no positional argument is called with none:

```
["udf","parse_price"]      f(value)
["udf","now"]              f()          # nullary: the upstream is ignored
```

A function with a **required** extra parameter (a second positional or a required keyword-only) cannot
be called this way and is a compile error `UP2-E1005` whose fix says to bind it at registration
(`functools.partial`) or to take a payload object; an optional extra parameter is fine and stays at
its default. An unregistered name stays `UP2-E1010`.

`ctx` injection is **removed**, together with `CtxView`, `Namespace`, the reserved parameter name and
the `def f(ctx, value)` ambiguity it created. Configuration travels in a payload the chain builds with
`ctx` (D11), so a host function is a pure value transformation and side effects are the chain's job
(`ctx.set`).

`udf` stays a separate operator from `py`: `py` is a closed allowlist shipped with the engine
(portable, deterministic, audited as 42 pairs), while `udf` is a host registry (open, and a chain
using it is not portable without that host). Folding it into `py` would make `py`'s action space
host-dependent and make `up2 ops`, the catalogue and the conformance report vary by host.

### D11 — `ctx.obj` names the value a stage received (decided 2026-11-08)

`ctx` gains a fourth **readable** root, `obj`: the value this stage received. It is resolved from the
`Call` the operator already holds (`call.value`), so there is no per-stage write, no reserved key in
`locals`, and nothing new appears in `ctx.locals`, the trace or the sandbox projection unless a chain
asks for it.

```
["ctx","get","obj"]
["ctx","dict",{"value":"obj","lang":"globals.lang"}]
["ctx","list",["obj","locals.x"]]
```

`ctx.set "obj"` / `ctx.del "obj"` are compile errors (`obj` is not a store), and `obj` names the whole
value only — reading a field is `["py","getitem",…]` after `ctx.get "obj"`, not `obj.x`. `obj` is a
value, not a scope, so it takes no path. The readable roots become `globals` / `locals` / `public` /
`obj`; the writable ones stay `locals` / `public`.

**`$obj`** is the same value's name on the **parameter** side (decided 2026-11-08). Refs are the only way
to name the incoming value inside a parameter tree, and there is a real ordering need: `or`/`and` put
the incoming value first, so "a saved candidate wins over the live value" is impossible without it.

```
["py","or",["$locals.meta_title","$locals.meta_desc","$obj"]]
```

`$obj` is the whole value — no path, for the same reason as `ctx.obj` — and is resolved from the
stage's `Call`, not from a scope, so it is a fifth ref root beside `globals` / `locals` / `public` /
`in` / `$<step>`. Reading it where no stage value exists (a story `call` step's `with` arguments) is
`UP2-E2001`. `$in` still names the **step** input and does not change per stage; `$obj` changes at
every stage — the two are kept apart deliberately.

This is what lets `udf` stay unary: a configured call is one payload stage plus one call

```
["ctx","dict",{"value":"obj","lang":"globals.lang"}]
["udf","translate"]
```

### D12 — `re`: `search` takes an optional group, `findall` follows Python, `sub` replaces (decided 2026-11-08)

The `group` action is removed; `search`'s parameter is the pattern or a two-element `[pattern, group]`
where `group` is an index or a name:

```
["re","search","\\d{4}-\\d{2}-\\d{2}"]                    # group 0
["re","search",["(?P<y>\\d{4})-\\d{2}","y"]]              # named group
["re","search",["(\\d{4})-(\\d{2})",2]]                   # index
```

A pattern with non-capturing groups and lookarounds needs no group at all, and multi-group
reformatting composes `search` (narrow the text) with `sub` (rewrite it) — which is why the separate
action earned nothing.

`findall` keeps Python's `re.findall` semantics: zero or one group answers the group values, two or
more answer one tuple per match. The only change is **encoding**: a tuple becomes an array, because
the value domain has no tuple. The current implementation returns the tuples unchanged, so such a
product fails at the exit with `UP2-E2003` — that is the bug this fixes, not a semantic change.

`search` with no match answers the shape's empty value — `""` for a text accessor — as `02` §6 defines,
so the empty-value convention does not change. A match that produces empty text is also `""`; the
ambiguity is accepted and `py.default` handles the fallback.

`sub` takes a two-element `[pattern, replacement]` and replaces every match (no `count`): a count is
an exotic case and belongs in `code`. Every `\N` / `\g<name>` in the replacement is checked at
compile time by running `re.sub(pattern, replacement, "")`, which raises `PatternError` for a bad
index and `IndexError` for an unknown name before any text is touched. A no-match `sub` returns the
input unchanged.

With `group` gone and `sub` on an array, the only two-parameter actions left are `re.search`,
`re.sub`, `py.replace` and `xpath`, all written as two-element arrays — so the parameter-name object
disappears from the grammar (D3 becomes: one value bare, two values in an array, an object only when
the argument itself is a data map).

### D13 — `ctx` semantics stay as they are, with `obj` added (decided 2026-11-08)

The five actions stay. The semantics are pinned so the spec can state them: a missing `get` path is
`UP2-E2001`; `set` creates missing parents (`locals.a.b` becomes `{"a":{"b":v}}`); `del` is cleanup —
a missing path is a no-op and only the leaf is removed; both `set` and `del` return the upstream value
so they can sit mid-chain. `ctx.get` stays even though a chain can open with `["$globals.x"]`, because
a reference cannot replace the value **mid**-chain, which is the only thing `get` adds.

### D14 — `py` semantics: Python names mean Python, options stay out (decided 2026-11-08)

- A parameter-less action is two slots (`["py","strip"]`), per D2.
- `bool` follows Python: any non-empty string is true. The web-truthiness table is **deleted** — no
  `truthy` replacement; a chain that needs `"false"`/`"no"` semantics compares explicitly.
- `first` / `last` stay as readable sugars over `getitem 0` / `getitem -1`; `flatten` stays.
- `from_json` stays for JSON text; other formats (YAML/TOML) would be a separate `load` operator with
  a format and an optional dependency, not more `py` actions.
- `html_to_markdown` takes no parameters. The library's option surface (images, links, heading style)
  is a third-party API, and exposing it would repeat the `maxsplit`/`lang` leak; a host that needs
  options registers a `udf` wrapper (`partial(convert, keep_images=True)`). Relative links are still
  completed by `py.urljoin`, because the library has no `base_url`.
- Type conversions stay separate actions: `["py","int"]` is two slots and shorter than
  `["py","convert","int"]`, the verb is discoverable in `up2 ops`, and the behavior is fixed at
  compile time. They are not one generic cast anyway — `str` is JSON semantics (a container becomes
  JSON text, `None` becomes `""`, a bool becomes `"true"`), while `int`/`float` follow Python's rules.
- `list` is **removed**: it parses JSON array text (or passes a list through), which is `from_json`
  with a type assertion, and it is not Python's `list` (`list("ab")` is two characters).
- `normalize_space` stays: it collapses `\s+` to one space **and** trims, in one stage; the
  `re.sub` + `strip` alternative is two stages and leaves the edges.
- `md5` is **added** for checksums/ETags — a non-security use, so the call carries `# noqa: S324`
  with the reason stated.
- `strip` gains an optional `chars` literal: `["py","strip"]` strips whitespace, `["py","strip","\"'"]`
  matches Python's `str.strip(chars)`.
- `strip_tags` is **removed**: its `<[^>]*>` implementation keeps script text and eats real text
  after a bare `<` (`"<script>alert(1)</script><p>a < b</p>"` → `"alert(1)a"`). HTML text extraction
  is the css recipe (`css remove "script,style"` → `css1 text`).
- `uniq` becomes O(n): a `set` for membership plus a list for order. (`morebuiltins` is not installed
  here, so its source could not be copied; this is the standard order-preserving O(n) algorithm for
  hashable scalars, which is what its item restriction already guarantees.)
- `or` / `and` **include the incoming value** as the first operand (`value or a or b`). Today they
  evaluate only the parameter array, so `["py","or",["","fallback"]]` on `"in"` answers `"fallback"`
  and the input disappears. The operand array already accepts `$` references, so a priority list is
  `["py","or",["$locals.a","$locals.b"]]`. **`default` is removed** — with the value participating,
  `or` is the fallback, and the null/`""`-only distinction earned nothing.
- `between` is added: `["py","between",[200,300]]` is `200 <= value < 300`, half-open, numbers only
  (no string ordering, no coercion).
- No `rsplit`: without `maxsplit`, `rsplit(sep)` equals `split(sep)`, and the last-segment idiom is
  `split` + `last` (the first-segment one is `split` + `first`).
- **A `datetime` is a legal value inside a chain.** The value model already allows host objects to flow
  between stages (`getattr` exists for exactly that); what is forbidden is **export**. So `strptime`
  may produce a `datetime` and `strftime` may consume one — that is Python's str↔date pair, and the
  earlier "the value domain has no datetime" claim confused *not exportable* with *cannot exist*.
  `pack` names the exit: a `datetime` product reports `UP2-E2003` with a fix that says
  `["py","strftime","…"]` rather than the generic "only JSON values" line.
- `strptime` is **added**: `["py","strptime","%d|%m|%Y"]` parses with an explicit, literal format and
  answers a `datetime` (naive; a `%z` in the format makes it aware). The format is validated at compile
  time (the same directive table `strftime` uses), so a typo is a pointer, not a runtime surprise; a
  text that does not match is `UP2-E2005` naming the format. There is no format guessing.
- `strftime` keeps its Python name (the earlier `format_time` rename is withdrawn): its input is a
  `datetime`, not a string. Locale-dependent directives (`%a`, `%b`, `%p`, `%c`, `%x`, `%X`) stay
  compile errors — their output is decided by the process locale, which would make a chain's result
  machine-dependent. `%z` is allowed and renders an aware value's offset (empty for a naive one);
  `%Z` stays rejected.
- `parse_time` is **deleted**: the action, its built-in format table, the `time` extra / `dateparser`
  dependency, and the `UP2-E2007` / `UP2-E2008` codes all go. With no guessing there is nothing left for
  it to do that `strptime` does not; relative and natural-language dates are out of scope (host `udf` /
  `code`), and the clock dependency that made it non-deterministic disappears with it.
- `slice` already covers the full Python form (`start:stop:step`, negatives, reverse), and `getitem`
  reads a dict by key, a list by index and a string by character (negative indices included).
- `find_jsons` is **added** (from `morebuiltins.utils`): scraping pages embed JSON in scripts
  (`__NEXT_DATA__`, `window.__INITIAL_STATE__`), and a regex cannot count nested braces. It returns the
  **parsed** objects/arrays in document order, so `getitem 0` or a `json` filter applies directly; a
  candidate that is not strict JSON is skipped. The scan is one stack-based pass — the donor
  implementation loops forever on an unmatched `{` (verified: `find_jsons('{unclosed')` does not
  return), so the algorithm is rewritten rather than copied.
- `from_timestamp` / `to_timestamp` are **added**: APIs speak epoch seconds, so the pair converts
  between an epoch and a `datetime`. `from_timestamp(ts, tz)` answers an **aware** datetime at the fixed
  offset `tz` (hours; a half-hour zone writes `5.5`); there is no timezone database and no DST.
  `to_timestamp(dt, tz)` uses an aware value's own offset, and interprets a **naive** value at `tz`
  (default `0`, i.e. UTC) — a deliberate deviation from Python's `datetime.timestamp()`, which would
  read the machine's local zone and make the result machine-dependent. A non-zero `tz` on an already
  aware value is `UP2-E2002` instead of a silent choice.
- Nothing else from that module is adopted: display formatting (`read_num`/`read_size`/`read_time`),
  base62 and int↔bytes conversion, `exec`-based `code_inline`, the host/OS helpers
  (`PathLock`, `FileDict`, `Clipboard`, pid files, `cut_file`) and the clock/random generators
  (`gen_id`, `SnowFlake`) are either presentation, outside the value domain, or non-deterministic.
  `get_hash` is `sha256` plus `slice`, and its non-string path (`str(obj)`) is ambiguous for dicts.
  `uniq` keeps the same set-plus-order algorithm as the module's key-less `unique`.

## Open items (to confirm before `specs`/`tasks`)

None. Both remaining questions are settled: `["json"]` is the canonical whole-document spelling
(`["json","@"]` stays legal), and `xpath`'s two parameters become an array
(`["xpath","text",["//dc:creator",{"dc":"…"}]]`), leaving no named-object parameter list in the
grammar.

## Migration

Old chains stop compiling with a pointer at the offending slot: `["py","strip",""]` reports the extra
slot, `["const", x]` keeps working, `["json", p]` keeps working, `{"key":…}` reports the retired key.
Stored graphs are read as before; only compilation changes, so a store rollback needs no data
migration. The generated catalogue and the 74 coverage declarations are regenerated in the same change.
