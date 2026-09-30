# Tasks

## 1. Field-map validation

- [x] 1.1 Declare `MAX_FIELDS_PER_MAP` (256) in `src/uniparser2/core/limits.py`, in the style of the
  neighbours (a one-line docstring saying what it bounds and which code it reports); Verification:
  `uv run python -c "from uniparser2.core.limits import MAX_FIELDS_PER_MAP"` exits 0
- [x] 1.2 Validate the map own shape in `src/uniparser2/core/compile.py::_resolve_field_map`: no fields ⇒
  `UP2-E1005`; an empty field name or one containing `.` ⇒ `UP2-E1005` at that key with the key named in
  the fix line; more than `MAX_FIELDS_PER_MAP` fields ⇒ `UP2-E1012` naming the count and the bound;
  Verification: the three new scenarios of the `dsl-operators` delta pass, and a map of exactly 256
  fields still compiles

## 2. One write path and the fallback wording

- [x] 2.1 Let `each` write a per-element local through `Scope.write_local` instead of assigning
  `scope.locals[name]` in `src/uniparser2/ops/basic.py`; Verification: `uv run pytest tests/ops/test_each.py`
  stays green and the `_t` scenario still yields no `_t` key
- [x] 2.2 Re-word the fallback rule in `src/uniparser2/core/refs.py` (the module docstring and the
  `Scope` docstring): fallback is by name — the innermost scope holding the first segment resolves the
  whole path; Verification: `_read_locals`'s own docstring, the module docstring and `docs/specs/003 §4.2`
  state the same rule, and `rg 'fall back outward' src/ docs/` returns only lines that state the
  name-level rule

## 3. Public-API nits

- [x] 3.1 Drop the positional-only marker from `loads` in `src/uniparser2/core/ast.py`; Verification:
  `loads(source=[["py","strip",""]])` returns the same stages as the positional call, asserted in a test
- [x] 3.2 Rename `Scope.chain()` to `Scope._lineage()` in `src/uniparser2/core/refs.py` and its single
  caller; Verification: `rg '\.chain\(\)' src/ tests/` finds no scope-lineage call, and
  `uv run pytest tests/core` is green

## 4. Tests and conformance

- [x] 4.1 Add the compile-time cases to `tests/compile/` (empty map, dotted name, empty name, 257 fields,
  256 fields accepted) and the keyword-`loads` case to `tests/core/` or `tests/serialization/`;
  Verification: `uv run pytest tests/compile tests/core tests/serialization` is green
- [x] 4.2 Add the non-fall-through case to `tests/ops/test_each.py` (an element's own `_a` does not expose
  an outer `_a`'s keys); Verification: the case fails if `_read_locals` is changed to per-key fallback
- [x] 4.3 Confirm the audit is unchanged — no operator, action or code is added; Verification:
  `uv run up2 conformance --check` reports 61 declared pairs = 61 covered pairs and 26 codes

## 5. Documentation

- [x] 5.1 `docs/specs/002-dsl-spec-triples-and-operators.md` (§3.2 / §6.9 wording, the scope sentence in
  §8's neighbour sections) and `docs/specs/003-parse-chain-spec.md` §4.2 state name-level fallback;
  `docs/operator-reference.md` likewise; Verification: each re-worded sentence names the first segment
  rule, and `rg 'first segment|by name' docs/specs/002* docs/specs/003* docs/operator-reference.md`
  reaches all of them
- [x] 5.2 `docs/specs/007-source-decisions-and-roadmap.md`: record the deferred cross-level `_`-name check
  as an open item of the node layer (beside the open `flat` export key), and note the field-map bound;
  Verification: the open-item section lists both, and the note's operator/code counts stay unchanged
- [x] 5.3 `CHANGELOG.md`: a `Fixed` entry for the review follow-ups (three compile-time rejections, the
  fallback wording, the two API nits); Verification: the entry names all four code files touched

## 6. Gates and wrap-up

- [x] 6.1 Run the definition of done in `AGENTS.md` plus the change-linter at the level this change
  warrants: `uv run ruff format --check`, `uv run ruff check`, `uv run mypy`,
  `uv run pytest --cov=uniparser2.core --cov-fail-under=95`, `uv run up2 conformance --check`;
  Verification: all five exit 0 and every axis of the graded check passes, with a missing tool reported
  truthfully (the type checkers need `VIRTUAL_ENV` cleared). Measured: all five green, coverage 98.67%,
  and the graded check ran at **L3 + S** with `--project-scope` (ruff ×2, complexity, ty, pyrefly,
  pyright, bandit — all pass)
- [x] 6.2 Validate and archive so the two deltas merge into `openspec/specs/`; Verification:
  `openspec validate each-review-followups --strict` passes, then `openspec list` reports no active
  change and `openspec validate --specs --strict` still passes for all five capabilities
