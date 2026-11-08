# Design

## Context

See `proposal.md` — Why. `pyops._check_scalar_params` walks `_SCALAR_PARAMS` — a table of
`action → {parameter: expected-prose}` — and rejects a value that is a `Mapping`, `list` or `tuple`.
The prose ("a string", "an integer") is documentation only, so a literal of another type gets through.
The two parameters whose runtime *parses* their string (`slice.spec`, `split.maxsplit`) are not parsed
here at all, so a value like `"bogus"` is discovered only when `_parse_slice_spec` / `int()` raise
inside evaluation.

## Goals / Non-Goals

**Goals:**

- One rule, stated and met: a literal the runtime will reject is rejected at compile time.
- No second implementation of a parser. The compile-time check must accept exactly what the runtime
  accepts, today and after any later change.

**Non-Goals:**

- Type-checking values only known at run time (a `$locals.x` reference). Nothing is claimed about them.
- Tightening parameters that merely **coerce** their value (`join.sep`, `parse_time.lang`,
  `py.default.value`): a coercion is not a rejection.
- A general schema/type system for `py`'s parameters (`07` §4-**h** keeps that decision deferred).

## Decisions

### D1 — The table carries the accepted types; the prose stays for the message

`_SCALAR_PARAMS` becomes `action → {parameter: (expected, accepted_types)}`. `accepted_types` is `None`
for a parameter that only needs the container check (`getitem.at`, "a scalar"). The prose keeps
producing the existing message, so the diagnostic text does not change for the cases that already
failed.

Only a `Lit` is inspected. A `Ref` is resolved during evaluation, and the existing comment in the
function already says so; the check must not invent a claim about it.

### D2 — The value checks call the runtime's own parser

`slice.spec` is validated by `_parse_slice_spec` — the same function `_py_slice` calls — and
`split.maxsplit` by a rule that mirrors `_int_param` (`bool` and `null` are not integers; `int(value)`
must succeed). Calling the runtime function is what keeps the two in step: a later change to the slice
syntax cannot leave the compiler behind.

`split.maxsplit` keeps its two "no limit" spellings: `null` and `""` are skipped before the check,
exactly as `_py_split` short-circuits them.

### D3 — `UP2-E1005`, the pointer and the existing fix derivation

The failure is a malformed parameter, not a bad value at run time, so it reports `UP2-E1005` at
`/0/2/<param>` with the fix line `_scalar_fix` already derives from the action's arity. Reusing both
keeps one vocabulary for "you wrote the parameter wrongly".

## Risks / Trade-offs

- **A wrong-typed literal starts failing at lint** where it used to fail at evaluation. Nothing that
  produced a value changes; the error code moves from `UP2-E2002` / `UP2-E2005` to `UP2-E1005`, and it
  arrives earlier, with a fix line where `urljoin`'s used to be empty.
- **A float for `maxsplit`** stays legal, because `int(1.5)` succeeds at run time. Mirroring the
  runtime is the goal; tightening it further would be a separate decision.
