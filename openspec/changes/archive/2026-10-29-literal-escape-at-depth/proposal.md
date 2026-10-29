# Proposal

## Why

`{"$lit": …}` is documented as *the* way to write a literal that starts with `$` in a
`ref_or_literal` parameter, but it is only recognised at the **top level of a parameter slot**.
Inside a container the same object is not a directive, so such a literal has no legal spelling —
and one of the two failure modes is silent:

- `["py","or",[{"$lit":"plain"},"b"]]` answers with the dict `{'$lit': 'plain'}`: the object is
  walked as data and leaks downstream as a value.
- `["py","or",[{"$lit":"$a"},"b"]]` and `["code",{"src":"…","inputs":{"a":{"$lit":"$k"}}}]` fail
  with `UP2-E1006 unknown reference root 'a'` / `'k'`, because the escaped text is resolved as a
  reference a second time.

The diagnostics make the same gap harder to find. An unknown root reports "use a reserved root, or
declare the earlier step product with --product" and never mentions the escape. A `$`-prefixed path
handed to `ctx` reports "the root `'$locals'` is not readable" with the fix "use globals / locals /
public" — true, but it does not say that the path is written **bare**, which is the actual mistake.

## What Changes

- **`{"$lit": …}` is recognised at every depth** of a `ref_or_literal` parameter. A single-key
  object whose key starts with `$` is a directive wherever it appears; `$lit` is the only directive
  that exists, and anything else `$`-prefixed reports the same `UP2-E1005` the slot-level form
  reports. `literal` parameters are untouched: there a `$` is text.
- **Three diagnostics name the way out**: an unknown reference root points at `{"$lit": …}`; the
  `ctx` read and write path diagnostics say to drop the leading `$` when the path has one.
- **No new syntax.** `${…}`, `$$` and `\$` were weighed and rejected: the first changes the spelling
  without adding capability and implies interpolation the DSL does not have; the second would mean
  two escapes to learn; the third cannot even be written in JSON (`"\$"` is not a JSON escape, so
  the source would be `"\\$100"`) and rewrites the payload instead of quoting it.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `dsl-operators`: the escape for a literal that starts with `$` applies at any depth of a
  `ref_or_literal` parameter, and the reference/path diagnostics SHALL state it.

## Impact

- Kernel: `core/compile.py` (`_resolve_param` gains the nested directive branch; the `UP2-E1006`
  fix line gains the escape), `ops/ctx.py` (the fix lines of `UP2-E1005` and `UP2-E1015`).
- Docs: note `02` §3.3 and §4, `docs/operator-reference.md`, `CHANGELOG.md`.
- Tests: the escape at depth in an array and in an object, the removal of the silent pass-through,
  the unsupported-directive error at depth, and the three diagnostics.
- **Behaviour narrowing**: a data object whose only key starts with `$` now reports a directive
  error at depth, where it used to pass through as data. The slot-level form already behaved this
  way; the escape is the way out.
