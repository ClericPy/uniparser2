# Proposal

## Why

L2 needs exactly one way to say "the stage above produced a list; turn every element into a
dictionary". The design draft `003` answers that need three times: the node-level `select` field
(§4.1), the `callback` operator with a chain named from a `presets` container (§4.3, `02` §6.9), and
the `$map` directive inside the `result` template (§6) — plus a `$item` scope root that exists only to
name the current element. So the same need has three spellings, two of which switch the per-element
context **implicitly** (a node field, a template directive), while the third needs a container, a
name-resolution pass and a second error class (a dangling name) to be referable at all.

Nothing is implemented, so the redesign costs a documentation rewrite plus one operator: measured on
this commit, `select` / `callback` / `presets` / `$map` / `MAX_MAP_*` appear nowhere under `src/`
(only inside comments and fix-line text), and `CODES` carries neither `UP2-E1105` nor `UP2-E1106` nor
`UP2-E2012`. There is no compatibility layer to write and no test to withdraw.

## What Changes

- A new operator **`each`** (arity 2, a single action, so a stage is written `["each", {…}]`): its input
  MUST be a list, its single argument is a **field map** (`field name → chain`), and its output is one
  dictionary per element (`list[dict]`). An empty list yields `[]`; a non-list input fails with
  `UP2-E2002`.
- The argument is **inline, never a name**. The `presets` container, the name-resolution pass and the
  dangling-name error class are not introduced. Reuse, if it is ever wanted, belongs to a later change's
  callable stage rather than to a second parameter shape.
- A new **structured parameter kind**: the compiler compiles every sub-chain recursively (so a
  diagnostic pointer reaches inside one: `/1/title/0/2`), and a field map nested deeper than
  `MAX_EACH_DEPTH` (3) fails at compile time with `UP2-E1012`.
- A new **per-element scope**: each element is evaluated in a fresh child of the calling scope; reads
  fall back outward, writes always land in the element's own scope, so one element can never observe
  another's temporary. A `_`-prefixed key of the field map is a per-element local: later fields of the
  same element can read it, and it MUST NOT appear in that element's dictionary.
- **BREAKING (design-level, nothing implemented changes)**: `select`, `callback`, `presets`, `$map` and
  `$map.as` leave the design drafts, together with lint L16's `$map.as` half, lint L20 (presets must not
  reference one another) and the pointer-based wording of L17/L11; `$item` stops being a reserved scope
  root, which deletes `_DEFERRED_ROOTS` / `_DEFERRED_FIX` and the `UP2-E1006` "deferred root" branch
  that existed only for it, and with them its test.
- One element's outcome stays inside that element: the effective policy is applied per element, and
  `each` never silently drops an element — an element whose fields all resolve to absent still appears
  as `{}`. Filtering elements is left to a future change.
- Two runtime limits: an input list longer than `MAX_EACH_ITER` (10 000) fails with `UP2-E2012` before
  anything is evaluated.

## Capabilities

### New Capabilities

- `chain-iteration`: the `each` operator — list-only input, the inline field map, one dictionary per
  element, the per-element scope with its `_`-prefixed locals, the per-element failure rule and the two
  limits.

### Modified Capabilities

- `dsl-operators`: a third parameter species joins the scalar/any-value pair — a parameter whose value
  is a **field map of chains**, validated recursively at compile time.

## Impact

- `src/uniparser2/ops/basic.py` — the `each` operator (arity 2, single action, the field-map parameter),
  next to `const`.
- `src/uniparser2/core/registry.py` — the new parameter kind and the sub-chain evaluation entry point
  that a structural operator needs on its call context.
- `src/uniparser2/core/compile.py` — the recursive compilation of a field map (pointers descend into
  sub-chains) and the compile-time nesting check; the removal of the `$item` deferred-root branch.
- `src/uniparser2/core/refs.py` — the child scope with outward read fallback; `RESERVED_ROOTS` shrinks
  from four roots to three.
- `src/uniparser2/core/evaluator.py` — per-element policy application.
- `src/uniparser2/core/errors.py` — `UP2-E2012` joins `CODES`; `src/uniparser2/core/limits.py` —
  `MAX_EACH_ITER` / `MAX_EACH_DEPTH`.
- `tests/` — the behaviour cases of the new operator, the compile-time rejections, the scope isolation
  cases and the withdrawn deferred-root case.
- `up2 conformance --check`: one new `(operator, action)` pair (60 → 61) and one new error code
  (25 → 26), both asserted.
- `docs/specs/003` (§4.1 removed, §4.2 gains the scope rule, §4.3 removed, §6 loses `$map`, §10 loses
  L16's second half and L20, §11 re-walked), `docs/specs/002` (the operator table gains `each`, §6.9
  becomes `each`, §3's scope table loses `item`, the error table drops two rows),
  `docs/specs/000` / `001` / `004` / `005` / `007` (the mentions of the removed mechanisms),
  `docs/operator-reference.md`, `CHANGELOG.md`.
- `src/uniparser2/__init__.py` — `0.2.0` → `0.3.0` (`005` §7: a new capability bumps the minor).
- Not in this change: the L2 node layer itself (`seed` / `parse` / `emit` execution, `routes`, `result`
  assembly, `up2 trial`'s node trace, the `UP2-E11xx` lint set). Its design notes are re-aligned here;
  its implementation is a following change.
