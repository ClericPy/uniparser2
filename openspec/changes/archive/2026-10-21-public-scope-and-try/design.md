# Design

## Context

See `proposal.md` — Why. The scope today has two halves with a hard rule each: `globals` is the
chain's constants (read-only, fingerprinted) and `locals` is private to the scope that wrote it (the
`Scope.locals` mapping, walked outward by name, `core/refs.py`). A stage's failure always stops the
chain; the settlement policy that once made it configurable is retired (`01` `D-01-1`) and the
action-level `accepts_missing` went with the third outcome (`empty-value-semantics`).

## Goals / Non-Goals

**Goals:**

- A place for run-scoped, cross-node state that is not chain data.
- A way for an author to say "this one stage may fail" without a run-wide policy.
- Both stay inside the kernel's rules: pure, synchronous, no IO.

**Non-Goals:**

- A step-level tolerance ("skip this answer, keep its reason") — a different semantic, decided
  separately.
- Turning an exception into a value (`str` / `repr` / literal policies).
- Making `globals` writable.

## Decisions

### D1 — `public` is a scope, not a variant of `globals`

`globals` is **chain data**: it is written in the bundle, it is covered by the fingerprint, and it
must not change during a run or "same chain, same result" stops being true. `public` is **runtime
state**: it is created empty by the run, it is never fingerprinted, and it dies with the run. That
separation is the whole reason it is a separate scope rather than a writable `globals`.

### D2 — `public` lives on the run's scope, not on the field scope

`Scope` gains a `public` mapping. The run's root scope owns it; a child scope (an `each` element)
**shares** it by reference, the way `globals` and `products` are shared — so a value written inside an
element is visible after the element, which is what "progress" means. `locals` stays per-scope.

### D3 — `try` is a directive the evaluator reads, not an operator

It is not an operator, so it is not a `py` action: it changes what the **evaluator** does with the
next stage's outcome, and the operators stay pure. The compiler recognises it as a stage shape (a
one-slot stage whose slot is a policy name), so `up2 ops` does not list it and the conformance audit
does not need a case for it — but the compile-time rules (no two in a row, none at the end) are
enforced like any other rule.

*Alternative rejected*: making it a `py` action with an `accepts_missing`-like flag — that puts the
policy in the operator layer, where a chain author could attach it to any action, and it is exactly
the mechanism the previous change removed.

### D4 — The guard is consumed by the next stage, success or failure

A `try` sets a one-shot guard; the next stage consumes it. On failure the policy applies; on success
the guard is simply gone. Two in a row is a compile error because the first would guard the second
(a directive, not a stage) — the rule is clearer than "the last one wins".

### D5 — `skip` and `break` keep a value the chain already had

`skip` continues with the value that was flowing into the failing stage; `break` ends the chain and
answers with that same value. Neither constructs a value out of the exception, so `01` §4.1 ("an
error is not a value") holds. The one thing that changes is **whether the run stops**.

## Risks / Trade-offs

- **`skip` hides a failure.** The trace still records the failed stage with its code and reason, so a
  skipped failure is visible in the trace and in `up2 trial --trace`; but a chain that skips a lot can
  produce an empty-looking product. The mitigation is the trace, plus the fact that the author wrote
  the `skip` explicitly.
- **`public` is invisible in the chain data.** A reader of the bundle cannot see what a run will
  carry; that is the point (it is runtime state), but it means a chain that depends on `public` is
  not reproducible from the bundle alone. A durable run records it (`03` §13 O6's journal).
- The `public` root is a new reserved word, so `$public` in an existing chain changes meaning. No
  committed chain uses it.
