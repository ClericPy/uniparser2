# Tasks

## 1. The field-map parameter kind

- [x] 1.1 Add the parameter kind to `src/uniparser2/core/registry.py` and resolve it in
  `core/compile.py::_resolve_param`: an object becomes `{field name: CompiledField}`, every value is
  compiled with `compile_field` (threading the enclosing `products` through, so the node layer can
  check a product reference inside a sub-chain later), and a value that is not an object is rejected
  with `UP2-E1005` and a fix line showing the accepted writing; Verification: `["each", "title"]` fails
  with `UP2-E1005` at the parameter, `[["each", {"title": [["py","strip",""]]}]]` compiles, and a
  malformed sub-chain reports its own code at a pointer that reaches inside the map
  (`/0/1/title/0/0`)
- [x] 1.2 Check the nesting depth while compiling a field map: deeper than `MAX_EACH_DEPTH` is
  `UP2-E1012` at compile time, reported at the innermost `each` stage; Verification: a chain with four
  nested `each` stages fails with `UP2-E1012`, and three nested stages compile
- [x] 1.3 Let each sub-chain respect the existing per-chain stage limit; Verification: a sub-chain of
  33 stages fails with `UP2-E1012` with a pointer inside the field map

## 2. The `each` operator

- [x] 2.1 Register `each` in `src/uniparser2/ops/basic.py` next to `const`: arity 2, one action, slot
  role `fields`, and the field-map parameter; Verification: `uv run up2 ops --json` reports `each` with
  arity 2 and the parameter-slot shape `value`, `["each", {"n": [["py","len",""]]}]` passes
  `uv run up2 lint`, and `["each", "each", {"n": []}]` fails with `UP2-E1004`
- [x] 2.2 Give the kernel's call context a sub-chain runner (design D2) and let `each` evaluate through
  it; Verification: `[["each", {"title": [["py","strip",""]]}]]` on `[" a "]` returns
  `[{"title": "a"}]` in a unit test, and `uv run mypy` stays clean with no new `Any` in the operator's
  signature
- [x] 2.3 Implement the contract: a list input yields one dictionary per element in input order, an
  empty list yields `[]`, a non-list input fails with `UP2-E2002` naming `each` and the type that
  arrived, and a missing input keeps the shared short-circuit (the operator does not accept missing);
  Verification: the four scenarios of the `each` requirement in the delta spec pass
- [x] 2.4 Build each element's dictionary from the field names that do not start with `_`, in
  declaration order, and store a `_`-prefixed field in that element's locals instead; Verification:
  the `_t` scenario yields `[{"a": "x", "b": "X"}]` with no `_t` key, and a later field of the same
  element reads the local an earlier field wrote

## 3. The per-element scope

- [x] 3.1 Give `Scope` a parent link in `src/uniparser2/core/refs.py`: reads fall back outward (the
  scope's own locals, then its parent's), writes and deletes stay in the scope they were asked for;
  Verification: `uv run pytest tests/ops/test_ctx.py` stays green, and a new case reads a local written
  by the calling scope from inside an element
- [x] 3.2 Evaluate every element in a fresh child scope of the calling scope; Verification: the three
  scope scenarios of the delta spec pass — an element local shadows the calling scope's value of the
  same name, an element reads a value from the calling scope, and a local written by an element is
  missing again after `each` returns

## 4. Limits and the new error code

- [x] 4.1 Declare `MAX_EACH_ITER` (10 000) and `MAX_EACH_DEPTH` (3) in
  `src/uniparser2/core/limits.py` (the module's docstring says limits land with their layer) and add
  `UP2-E2012` to `CODES` in `src/uniparser2/core/errors.py`; Verification: `uv run up2 conformance
  --check` reports 26 implemented error codes, and a case asserts `UP2-E2012`
- [x] 4.2 Check the length of the input list before evaluating any element; Verification: a list of
  10 001 elements fails with `UP2-E2012` with `py.slice` named in the fix line, and the same list whose
  elements would fail anyway still reports `UP2-E2012` (the limit is decided first)

## 5. Tests and conformance

- [x] 5.1 Add `tests/ops/test_each.py` with the behaviour and scope scenarios of the delta spec and the
  `("each", "each")` coverage declaration; Verification: `uv run pytest tests/ops/test_each.py` is
  green and `uv run up2 conformance --check` reports 61 declared pairs, 61 covered pairs
- [x] 5.2 Add the compile-time cases (`UP2-E1005` for a non-object argument, the deep pointer for a
  malformed sub-chain, `UP2-E1012` for the depth and for a sub-chain over the stage limit) to
  `tests/compile/`; Verification: `uv run pytest tests/compile` is green
- [x] 5.3 Withdraw the `$item` deferred-root branch from `src/uniparser2/core/compile.py` and
  `RESERVED_ROOTS` from `src/uniparser2/core/refs.py`, and turn
  `tests/compile/test_errors.py::test_e1006_deferred_item_root` into a case for what remains: an
  unknown root reports `UP2-E1006` listing the three roots; Verification: `uv run pytest
  tests/compile/test_errors.py` is green, and no source file mentions `$item` or `$map` any more
- [x] 5.4 Update `tools/demo_report.py` (the operator catalogue: a worked `each` case) and re-render
  the committed catalogue, which embeds the package version; Verification: `uv run python
  tools/demo_report.py` exits 0 with no "not Ok" warning, and `UP2_UPDATE_REPORT=1 uv run pytest
  tests/report` followed by a plain `uv run pytest tests/report` is green

## 6. Documentation

- [x] 6.1 `docs/specs/002-dsl-spec-triples-and-operators.md`: add `each` to the operator table (arity
  2, one action, the field map), replace §6.9 (`callback`) with an `each` section, drop the `item` row
  from §3's scope table, and correct the error table (`UP2-E2012`'s new wording, the `$map`/presets
  rows); Verification: every example chain in the note passes `uv run up2 lint`, the operator count in
  the note matches `uv run up2 ops --json`, and `rg '\$map|callback|presets' docs/specs/002*` returns
  only the retirement records
- [x] 6.2 `docs/specs/003-parse-chain-spec.md`: delete §4.1 (`select`) and §4.3 (`presets`), add the
  per-element scope rule to §4.2, delete `$map` from §6, update §10 (L11's `$item` mention, L16's
  `$map.as` half, L17's container list, L20) and re-walk §11 with `each`; Verification:
  `rg '\$map|\$item|select|callback|presets' docs/specs/003*` returns only the retirement records and
  the walkthrough's new chains, and each chain in the walkthrough is checked against the operator table
- [x] 6.3 The remaining notes: `000` (the field row), `001` (the bounds rule), `004` (the `_`-prefix
  guidance), `005` (the L2 checklist entries for the retired mechanisms), `007` (the Adopt list and the
  operator count); Verification: `rg '\$map|callback|presets|\$item' docs/specs/000* docs/specs/001*
  docs/specs/004* docs/specs/005* docs/specs/007*` returns only contexts that state the retirement
- [x] 6.4 `docs/operator-reference.md` (an `each` entry with worked examples), both READMEs (the
  operator list), `CHANGELOG.md` (Added / Changed / Removed) and `src/uniparser2/__init__.py`
  (`__version__ = "0.3.0"`); Verification: `uv run up2 --version` prints `0.3.0`, and the operator
  lists in the reference page and both READMEs match `uv run up2 ops --json`

## 7. Gates and wrap-up

- [x] 7.1 Run the definition of done in `AGENTS.md` plus the graded post-edit checks of the
  change-linter at L2: `uv run ruff format --check`, `uv run ruff check`, `uv run mypy`,
  `uv run pytest --cov=uniparser2.core --cov-fail-under=95`, `uv run up2 conformance --check`;
  Verification: all five commands exit 0 and every L2 axis passes, with a missing tool or an
  unrunnable axis reported truthfully. The graded check was run at **L3 + S** (the change moves public
  signatures — `Call`, `Scope`, `Kind`, `compile_field`): ruff, complexity, ty, pyrefly, pyright and
  bandit all pass (the type checkers need `VIRTUAL_ENV` cleared, otherwise they resolve a polluting
  uv-cache environment and cannot find `pytest`)
- [x] 7.2 Validate and archive the change so its deltas merge into `openspec/specs/`; Verification:
  `openspec validate l2-chain-structure-and-each --strict` passes, then `openspec list` reports no
  active change, `openspec list --specs` lists `chain-iteration`, and `openspec validate --specs` passes
- [x] 7.3 Keep a count-bearing OpenSpec scenario from going stale again: the `code-execution` scenario
  that hard-coded "59 declared pairs = 59 covered pairs" now compares the declared total with the
  registry's own number; Verification: `openspec validate --specs` passes and no spec under
  `openspec/specs/` states a literal pair count
