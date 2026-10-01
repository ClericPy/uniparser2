# Design

## D1 — The comparisons live in `py`, not in a new `cmp` operator

`py` is the standard-library allowlist: one entry point, pure functions, JSON in and JSON out, and the
conformance audit already tracks a pair per action. `operator.eq` … `operator.ge` are exactly that, and
their one parameter writes the same way `py.urljoin`'s does (`["py","==",200]`, `["py","==","$globals.limit"]`).
A separate operator would duplicate the whole parameter-slot machinery for six one-parameter actions.

Rejected: a single `py.cmp` returning `-1`/`0`/`1` — three meanings in one action, and a chain that
reads `["py","cmp",10]` no longer says which comparison it means.

## D2 — `eq`/`ne` are total, ordering is partial

JSON has no total order across types, and Python answers `1 < "a"` with a `TypeError`. Left alone that
escapes as `UP2-E2099` ("operator raised an unexpected exception"), which tells the chain author nothing
about which operand was wrong. So the four ordering actions check comparability first (both numbers, or
both strings) and report `UP2-E2002` naming both types. `eq`/`ne` need no such check: `==` is total in
Python and the spec fixes the answer for mixed types (`200` is not `"200"`), which is the behaviour a
predicate wants.

## D3 — `exists` joins the selector family, and only it

`css`/`css1` are 3-slot operators whose action table is shared (`text`, `html`, `outer_html`, `self`,
`nodes`, `remove`, `@<attribute>`), so a new action costs one entry and reaches both operators.

The neighbours cannot follow: `json` and `xpath` are **arity-2 single-action** operators — their writing
is `["json", expr]` / `["xpath", expr]` with the action slot omitted — so a second action would require
the action slot and break every existing chain. The asymmetry is recorded rather than papered over: JSON
and XML existence waits for a sibling operator or a grammar change, and today's workaround
(`["json","path"]` under `on_missing="empty"` plus `["py","!=",""]`) is policy-dependent and therefore
not documented as the way to do it.

## D4 — Why `exists` is needed at all

Measured on this commit, the existence idiom built from `nodes` is policy-dependent:

| Chain | `on_missing="empty"` | `"drop"` | `"raise"` |
|---|---|---|---|
| `[["css","nodes",".nope"]]` | `Ok("")` | `Missing` | failure |
| `[["css","nodes",".nope"],["py","bool",""]]` | `Ok("")` — `bool` never runs | `Missing` | failure |
| `[["css","nodes",".nope"],["py","default",false],["py","bool",""]]` | `Ok(False)` | `Ok(False)` | `Ok(False)` |

Only the three-stage form is stable, and it only works because `py.default` catches the missing value.
`exists` answers `true`/`false` directly, which is what a `match` predicate needs.

## D6 — `or`/`and` follow Python; `all`/`any` and `not` are not added

Two families, and the difference is what the answer **is**:

| Family | Actions | Answer |
|---|---|---|
| Value selection | `or`, `and` | one of the **operands** (Python's semantics) |
| Boolean judgement | `==`/`!=`/`<`/`<=`/`>`/`>=`, `in`, `exists` | a boolean |

The first version of this section proposed `all`/`any` with strict booleans. That cannot express the
shape extraction chains actually need — "take the first candidate that is not empty" (`title` from
`h1`, else from `meta[og:title]`, else a literal) — because a boolean answer throws the operand away.
Once `or`/`and` answer with the operand, boolean use is already covered (booleans in, boolean out), so
`all`/`any` would be a second spelling of the same thing (`any([b1,b2])` ≡ `or`).

A `not` action was in the first draft and is also left out: with a boolean-producing action in hand,
negation is `["py","!=",true]` — `!=` compares a value against a boolean literal — so `not` would be
another second spelling. Dropping it costs one action and keeps the surface at "one way to say each
thing"; if a plain `not` is ever wanted for readability, it is a one-line addition later.

Eager, for the usual reason: the operands are values the field map already computed into `_` locals
(an array resolves leaf by leaf by kind, `02` §3.3), so no new parameter kind and no new machinery is
needed. The price is no short-circuit; ordering candidates cheapest-first keeps that visible, and a
lazy structural operator carrying sub-chains is the L2 answer if candidates ever get expensive.

Strictness lives at the boundary, not in the combinator: `or` over `["", 0]` answers `0` (Python's
answer), and the place that requires a boolean is `match` in L2. Keeping the combinator
Python-faithful is what lets one action serve both selection and judgement.

Relation to `py.default`: `default` is the binary, **emptiness**-based fallback (`None`, `""`, missing);
`or` is the n-ary, **truthiness**-based one (it also covers `0`, `[]`, `{}`). Both stay, and the
reference page says which to reach for.

## D5 — `in` keeps Python's order, and no boolean algebra over chains

- The membership action is spelled `in` because that is Python's operator, and it keeps Python's
  **operand order**: the value on the left is the element, the parameter on the right is the container.
  `["py","in",[200,301,302]]` therefore asks "is the value one of those", and the "does the URL contain
  `/public/`" reading is written with the element in front
  (`[["const","/public/"],["py","in","$locals.url"]]`). A `contains`-flavoured action (the container on
  the left, the element as the parameter) would be the same action with the operands swapped, i.e. a
  second spelling.
- `and` / `or` over **sub-chains** (as opposed to over already-computed operands, which D6 provides)
  belong to the L2 `match` grammar, where whole chains can be composed lazily and can short-circuit.
  Until that lands, the eager array form of D6 covers the same need without a second machinery.
