# Proposal

## Why

Routing and validation both need **predicates**, and the operator layer has none: `up2 ops --json`
declares no `==`/`!=`/`<`/`<=`/`>`/`>=`, no `in`, and no `exists`. Measured on this commit:

- `["css","nodes",S], ["py","bool",""]` is **not** a usable existence test — `css nodes` reports
  `Missing` ("no node matched") when nothing matches, so the stage short-circuits before `py.bool`
  runs and the outcome is whatever the missing policy says (`""` under the default, `Missing` under
  `drop`, a failure under `raise`). The only working idiom today is three stages long
  (`[["css","nodes",S],["py","default",false],["py","bool",""]]`, measured `False`/`True`).
- Comparing a status code (or any value) has no writing at all: the only way today is a `code`
  sandbox stage, which is heavy for a one-line predicate.

The coming L2 dispatch wants `match` to be a chain that produces a boolean, and the "which parse rule
fits this response" question wants exactly these checks. They are one-line pure functions over the
standard library, so they belong in the operator layer before any of that design is fixed.

## What Changes

- **Seven `py` actions** (pure, stdlib, no optional dependency), all spelled the way Python spells them:
  `==` / `!=` / `<` / `<=` / `>` / `>=` — compare the upstream value with the single parameter (literal
  or reference, the `py.urljoin` writing) — and `in` — Python's membership test, with the **parameter** as
  the container (a substring, a list member, a dict key). `!=` against a boolean is the negation, which
  is why no `not` action is added.
- **Two logic actions** `or` / `and` with **Python's own semantics**: `or` answers with the first
  truthy operand, otherwise the last one; `and` with the first falsy operand, otherwise the last. They
  take one parameter that is an **array of references or literals** — the values the field map already
  computed into `_` locals — so `[["py","or",["$locals._a","$locals._b"]]]` is the "take A, else B"
  shape. Truthiness follows Python (`""`, `0`, `[]`, `{}`, `null`, `false`), because answering with the
  chosen operand is the point: a boolean is enforced at the predicate boundary (the L2 `match`), not by
  the combinator. They are **eager** — the operands already exist, so there is no short-circuit; that is
  the price of keeping this in `py` instead of a structural operator that carries sub-chains.
- Ordering comparisons accept **comparable pairs only** (both numbers, or both strings); anything else
  is `UP2-E2002` naming both types, instead of a Python `TypeError` escaping as `UP2-E2099`.
- **`exists` joins the selector family** (`css` / `css1`): true when the selector matches at least one
  node, **never `Missing`** — which is the point, because that is exactly what `nodes` reports today.
- **No new error codes**: type mismatches reuse `UP2-E2002`, and the missing-value policy is untouched.
- **No `not`** (a boolean plus `!=` covers negation) and **no boolean-algebra actions over sub-chains**
  (the L2 `match` grammar carries those, where whole chains can be composed lazily).
- `json` / `xpath` do **not** get `exists`: both are arity-2 single-action operators, so adding an
  action would break their existing writing (`["json", expr]`). Recorded as a known asymmetry with a
  follow-up note.

## Capabilities

### New Capabilities

- `predicates`: the chain-facing contract of boolean checks — one-stage comparison, containment and
  existence, all pure, all returning a boolean rather than leaning on the missing-value policy.

## Impact

- `src/uniparser2/ops/pyops.py` — seven `_TABLE` entries plus their implementations.
- `src/uniparser2/ops/htmldom.py` — the `exists` action on the shared selector table (so `css` and
  `css1` both get it).
- `tests/ops/test_predicates.py` (new), `tests/ops/test_registry.py` (the declared counts),
  `tests/require` / coverage declarations for the new pairs.
- `tools/demo_report.py` (one case per new pair) and the re-rendered `docs/report/up2-report.md`.
- `docs/specs/002` (§6.x `py` table: the function count 32 → 39 and the new rows), `docs/specs/005`
  (the measured pair count 61 → 70), `docs/operator-reference.md`, `CHANGELOG.md`.
- `src/uniparser2/__init__.py` — `0.3.0` → `0.4.0` (`005` §7: a new capability bumps the minor).
- `up2 conformance --check`: 61 → 72 declared pairs (eleven new: nine `py` actions plus `exists` on
  `css` and `css1`), 26 error codes unchanged, and `py`'s own action count 32 → 41.

## Not in this change

The L2 node-layer design (`match`, typed products, declared routing). This change only gives it the
predicates it will need.
