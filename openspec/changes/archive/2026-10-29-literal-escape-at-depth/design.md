# Design

## Context

See `proposal.md` — Why. `02` §4 fixes the decision order of the parameter slot's object form: "an
object with exactly one key, and that key starts with `$`, is a directive object (`$lit`)". §3.3
adds that **elements and values inside arrays and objects are resolved leaf by leaf** — which is
what a container walks, and a dict is not a leaf. So `_resolve_param` recurses into a dict's values,
never asking whether the dict itself is a directive, and `_directive_params` (the only reader of
`$lit`) runs in the slot path only.

## Goals / Non-Goals

**Goals:**

- One rule for the escape, at every depth. A literal that starts with `$` must be writable wherever
  a `ref_or_literal` value is expected.
- No silent pass-through: a shape the compiler does not understand is an error, never data.
- Every diagnostic about a `$`-prefixed mistake names the way out.

**Non-Goals:**

- Interpolation (`"https://x/${p}/"`), `$$`, `\$` — rejected in the proposal, on record here.
- Making `literal` parameters accept references; the compile-time validation they carry is the
  reason they are literal.
- Compile-time validation for `split.maxsplit` / `slice.spec`; they fail loudly at evaluation
  (`UP2-E2005`) today, which is a separate improvement.

## Decisions

### D1 — The directive rule is the slot rule, applied at every depth

`_resolve_param`'s dict branch asks `_directive_name` first. `$lit` yields a `Lit`; any other
`$`-prefixed single key raises the same `UP2-E1005` the slot form raises, with a fix line naming
`{"$lit": …}`. Reusing the slot's rule keeps `02`'s "one sentence" property (D-02-6): a leading `$`
means a reference, `{"$lit": …}` quotes it, everything else is data — the sentence does not change,
only the set of positions it is applied to.

The kinds are untouched: `Kind.FIELDS` (an `each` field map) is compiled before the dict branch, so
a field named `$lit` stays a field; `Kind.LITERAL` returns `Lit(raw)` before the branch, so a
literal parameter keeps `$` as text; `Kind.REF` reaches `_resolve_leaf` and reports `UP2-E1007`,
because a parameter that must be a reference cannot be a literal.

### D2 — A `$`-prefixed single-key object is a directive at depth, not data

This **narrows** behaviour: `{"$price": 1}` used to pass through as a value and now reports an
unsupported directive. Accepted because the alternative is worse — the same object at the slot level
already errors, and the silent pass-through is what produced `{'$lit': 'plain'}` downstream. The
error names `{"$lit": …}` as the escape, so the way out is one edit away.

### D3 — The `UP2-E1006` fix line always mentions the escape

Conditionally appending it ("if you meant text…") costs a branch and an extra sentence in the
message; always appending keeps the message two clauses and covers the common case, which is exactly
a user typing `"$100"` where the compiler sees a reference to a root called `100`.

### D4 — The `ctx` hint is conditional on the leading `$`

`ctx` takes a bare path by design (`02` §6.8): the `$` in a `ref_or_literal` slot exists to
distinguish a reference from a literal, and a `ctx` argument has no literal branch — it is always a
path. When the path *does* start with `$`, the mistake is specific and the hint says so ("drop the
leading `$`: `ctx` takes a bare path"); otherwise it keeps the write-surface message, which is about
a genuinely wrong root.

## Risks / Trade-offs

- **The narrowing in D2 could reject a real payload** whose only key starts with `$` (a JSON Schema
  fragment is the realistic example). The fix is `{"$lit": …}`, and the same payload was already
  rejected at the slot level, so the rule is now uniform rather than newly strict.
- **A nested `$lit` is no longer visible as data** when reviewing a chain: `{"$lit": "$100"}` reads
  as what it means, which is the point of a structural escape.

## Migration Plan

None. Every chain that compiled before either produces the same value or was already relying on the
silent pass-through that this change removes (and answered with a dict where a string was meant).
