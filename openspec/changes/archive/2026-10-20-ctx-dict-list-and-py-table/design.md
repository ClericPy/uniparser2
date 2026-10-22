# Design

## Context

See `proposal.md` — Why. `ctx.map` dispatches on the shape of its parameter (`_collect_paths`): an array
yields a list, an object yields a dict. The `py` table holds 41 actions and none of them turns a mapping
into an iterable, while `each` requires a list and `py.list` refuses a mapping; `code` can do it, but only
with the optional sandbox installed.

## Goals / Non-Goals

**Goals:**

- One action, one result shape: the name states what comes out.
- A zero-dependency path from a mapping to something `each` can iterate.
- A failure's fix text describes the input, not a workaround.

**Non-Goals:**

- A general `*` / `**` unpacking syntax for `call` (a later decision; this change only makes the two
  shapes buildable).
- Reworking the `py` namespace (it stays one operator with a table).

## Decisions

### D1 — Split `map` into `dict` and `list`

The dispatch on the parameter's shape is the whole problem: the same action answers two different types.
Two actions make the type visible at the call site, and each maps to one positional/keyword payload.

### D2 — The names are `dict` and `list`

They state the result and match the shape names a reader already knows. This deviates from the
`get` / `set` / `del` verb family; the deviation is accepted because the family's verbs describe an
operation on the scope, while these two describe a construction.

### D3 — `py.items` yields `[[key, value], …]`

Pairs as two-element lists, never tuples: the value domain is JSON, and a tuple is not a JSON value.
The mapping's own order is preserved, matching Python's `dict.items()`.

### D4 — Feeding `each` needs the literal indices `0` / `1`

`py.getitem` deliberately does not coerce its `at` parameter, so a pair field is
`["py","getitem",0]`, not `["py","getitem","0"]`. The action's summary and the operator reference say so.

### D5 — A conversion fix states the expected input

`str` / `int` / `float` / `bool` / `list` / `from_json` share `_convert`; its `fix` currently recommends
`py.default`, which cannot catch a failure and which would hide the bug if it could. The rule is: a fix
text names the accepted input and the upstream stage to check.

## Risks / Trade-offs

- **`ctx.map` is a breaking change.** No committed sample writes it; the tests and the notes do.
- **`py` grows to 42 actions.** The conformance audit and the report must list the new one.
- **`items` on a non-mapping** fails rather than coercing, which keeps "one action, one input shape".
