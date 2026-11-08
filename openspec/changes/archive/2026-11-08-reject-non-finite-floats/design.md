# Design

## Context

See `proposal.md` — Why. `values.is_json_value` is the one predicate behind the exit packing rule
(`export.pack`), the `udf` / `code` return checks (`UP2-E2009`) and the sandbox input check. It tests
`isinstance(value, (str, bool, int, float))`, so the non-finite floats pass. `ast.dumps` writes with
`json.dumps`'s default `allow_nan=True`, and `ast.loads` reads with Python's permissive decoder, so
chain text can carry them as well.

## Goals / Non-Goals

**Goals:**

- One definition of "a JSON value", used by every boundary, that matches what a strict JSON encoder
  writes.
- The failure is a diagnostic with a pointer, not a `ValueError` from the stdlib encoder.

**Non-Goals:**

- Rejecting non-finite floats inside a computation: `py.float("1e999")` keeps answering `inf`; the
  arithmetic is Python's, and only the boundary is ours.
- A general number-precision policy (large ints stay legal: JSON allows them).

## Decisions

### D1 — Fix the predicate, at the boundary it already guards

`is_json_value` becomes `math.isfinite` for a float. Every caller then inherits the rule: `pack`
reports `UP2-E2003` at the step that produced the value, `udf` / `code` report `UP2-E2009` when a host
function or a snippet returns one, and the sandbox refuses one as an input. Editing the producers
(`py.float`, `code`) instead would leave the other three surfaces open and would put an exit rule in
the middle of the chain.

### D2 — Chain text gets the same rule, with its own code

A chain is JSON text, so `loads` must not accept a constant JSON does not have. Python's decoder calls
`parse_constant` for exactly `-Infinity` / `Infinity` / `NaN`, so that hook raises `UP2-E1004` — the
"the chain text is not usable" family — instead of letting a non-JSON float into a stage parameter.
`dumps` passes `allow_nan=False` and converts the encoder's `ValueError` into the same code, so a
hand-built Python structure cannot produce invalid text either.

Two codes, one rule: `UP2-E2003` when a **product** carries it (the exit), `UP2-E1004` when **chain
text** carries it (the parser). Each names the surface the reader has to fix.

### D3 — The message says why

"only str / int / float / bool / null / list / dict may be exported" is true and misleading — a float
*is* allowed, just not this one. The fix line gains "and a float must be finite", and the reason names
the value (`float (inf)` through the existing preview).

## Risks / Trade-offs

- **A chain that ends with `inf` now fails** where it used to emit `Infinity`. That output was not
  JSON, so no correct consumer could read it; failing at the exit with a pointer is the fix.
- **A snapshot recorded before this change** could contain `Infinity` in its expected product;
  `loads` now refuses it, so such a case must be re-recorded. None exists in this repository.
