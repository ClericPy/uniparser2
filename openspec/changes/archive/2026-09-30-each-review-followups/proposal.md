# Proposal

## Why

A deep review of the `each` change (commits `9921ef1`, `06fc57e`) left one Major and five Minor items.

The Major: `_resolve_field_map` compiles one sub-chain per field with **no bound** on how many fields a
map may hold — measured on this commit, 1 000 / 5 000 / 20 000 fields compile in 10.8 / 55.4 / 241.2 ms
and produce the same number of sub-stages, while `MAX_STEPS_PER_FIELD` bounds only a **single** chain.

The Minor items: the scope documentation promises a read fallback the code does not implement (a path is
resolved by the scope that owns its **first segment**); a `_` name containing `.` compiles into a key no
reference can ever reach; `each` writes `scope.locals` directly instead of through `Scope.write_local`;
`loads(source=…)` raises `TypeError` although `loads` is public (`core/__init__.py` lists it in
`__all__`); `Scope.chain()` overloads this repository's "chain" vocabulary and has a single caller; and
`["each", {}]` compiles into a loop that can only return empty dictionaries.

Nothing is released yet (0 tags, not on PyPI), so the compile-time rejections added here need no
compatibility layer.

## What Changes

- The field-map parameter gains three compile-time rules in `_resolve_field_map`: a map with **no** fields
  is rejected, a field name that is empty or contains `.` is rejected (both `UP2-E1005`, with a fix line
  naming the accepted writing), and a map holding more than `MAX_FIELDS_PER_MAP` (256) fields is rejected
  with `UP2-E1012`.
- **No new error code.** The field bound is a resource limit exactly like `MAX_STEPS_PER_FIELD` and
  `MAX_EACH_DEPTH`, so it reuses `UP2-E1012`; the two name rules are schema validation, which
  `_resolve_field_map` already reports as `UP2-E1005`. `002 §7.1` retires codes that add a branch without
  adding information.
- The scope rule is stated as implemented: **fallback is by name**. The innermost scope that holds the
  first segment of a path resolves the whole path, so a key missing under a name the current scope wrote
  does **not** fall through to an outer scope holding the same name; a name the current scope did not
  write falls back outward as before. `docs/specs/002`, `docs/specs/003`, `docs/operator-reference.md`
  and two docstrings are re-worded.
- Chain authors keep a `_` name unique across nesting levels. A compile-time collision check is
  deliberately **not** added here: it must also see an L2 node's `fields` names, so it belongs to the node
  layer (recorded as an open item in `007`).
- `each` writes its per-element locals through `Scope.write_local`, so the operator stops bypassing the
  scope's write path.
- `loads` accepts `source` by keyword again; `Scope.chain()` becomes the private `Scope._lineage()`.
- **BREAKING (design-level, nothing released)**: an empty, oversized or dotted-name field map now fails
  at compile time instead of silently producing an unreachable key or an arbitrarily expensive compile.

## Capabilities

### Modified Capabilities

- `dsl-operators`: the field-map parameter requirement gains the non-empty rule, the addressable-name rule
  and the field-count bound.
- `chain-iteration`: the per-element scope requirement states name-level fallback and gains a scenario for
  a key that must not fall through to an outer scope holding the same name.

## Impact

- `src/uniparser2/core/compile.py` — `_resolve_field_map` (three validations).
- `src/uniparser2/core/limits.py` — `MAX_FIELDS_PER_MAP`.
- `src/uniparser2/core/ast.py` — `loads` loses its positional-only marker.
- `src/uniparser2/core/refs.py` — `Scope.chain()` → `Scope._lineage()`, and the fallback wording in two
  docstrings.
- `src/uniparser2/ops/basic.py` — the element-local write goes through `Scope.write_local`.
- `tests/` — the three compile-time rejections, a keyword `loads` call, and the non-fall-through case.
- `docs/specs/002`, `docs/specs/003`, `docs/specs/007`, `docs/operator-reference.md`.
- `up2 conformance --check` keeps its 61 declared pairs and 26 error codes (no operator, action or code is
  added).
