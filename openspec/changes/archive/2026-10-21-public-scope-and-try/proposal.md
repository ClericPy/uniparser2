# Proposal

## Why

Two gaps keep the chain model from carrying what a real crawl needs, and both are cheap to close.

First, a run has no place to **share** something across nodes. `globals` is the chain's read-only
constants (it is covered by the fingerprint, so writing it would break "same chain, same result"),
and `locals` is private to the field that wrote it. A crawl that must remember "which page I am on"
or "how many items are done" has nowhere to put it: `locals` is not readable from the next node
(`$locals._x` resolves in the writing node's scope), and there is no third scope.

Second, a stage that **fails** always stops the chain, with no way for the author to say "this one
field may fail, keep the value I already have". The settlement policy that once offered that was
retired (`01` `D-01-1`), and the action-level `accepts_missing` went with the third outcome
(`empty-value-semantics`) — so today there is no local tolerance at all, and one bad detail page
kills a whole batch.

## What Changes

- **A third scope, `public`**: readable and writable from any node of the run, living for the run.
  `ctx.set public.x` writes it, `$public.x` reads it, and `ctx.list` / `ctx.dict` may collect it. It
  is **not** part of the chain data, so it never enters the fingerprint. **BREAKING** (a new reserved
  reference root; `globals` / `locals` / `in` are unaffected).
- **A `try` stage**: a directive that guards **the next stage only**. When that stage fails, the
  policy decides: `raise` (the default, and the same as not writing it), `skip` (keep the value the
  chain already had and carry on), `break` (end the chain there and answer with the value in hand).
  A guarded stage that succeeds **disarms the guard**, so a `try` never leaks over a later failure.
- **The three policies are control, not degradation**: `skip` and `break` keep a value the chain
  already had; neither turns an exception into a value. The `str` / `repr` / literal policies are
  **not** adopted.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `chain-iteration`: the scope table gains `public`; the field map's local rule is unchanged; the
  `try` directive and its policies are specified.
- `core-evaluator`: the outcome model gains the `try` directive and the `public` root; a failed
  stage's default outcome is unchanged.

## Impact

- Kernel: `core/refs.py` (the `public` root, the scope's `public` mapping), `core/evaluator.py` (the
  `try` directive), `core/registry.py` + `core/compile.py` (the directive's declaration), `ops/ctx.py`
  (the writable roots), `core/story.py` (the run's `public` scope).
- Docs: notes `01` §4 and `03` §8, `02` §5 and §6.8, `docs/operator-reference.md`, both READMEs,
  `CHANGELOG.md`.
- Tests: the new root's read/write rules, the directive's three policies, and the compile-time rules
  that reject a malformed `try`.
