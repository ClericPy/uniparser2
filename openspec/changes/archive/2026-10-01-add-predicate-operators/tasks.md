# Tasks

## 1. The actions

- [x] 1.1 Add `==` / `!=` / `<` / `<=` / `>` / `>=` to `src/uniparser2/ops/pyops.py`: one
  `REF_OR_LITERAL` parameter (so a reference writes like `py.urljoin`'s), a boolean result, and deep
  equality for containers; Verification: `["py","==",200]` on `200` is `true`, on `"200"` is `false`,
  and `["py","==","$locals._n"]` resolves the reference (`tests/ops/test_predicates.py`)
- [x] 1.2 Check comparability in the four ordering actions and report `UP2-E2002` naming both types
  instead of letting a `TypeError` escape as `UP2-E2099`; Verification: `["py","<",10]` on `"abc"` is
  `UP2-E2002` with `str` and `int` in the reason
- [x] 1.3 Add `in` with **Python's operand order** (the parameter is the container): a `str` substring, a
  `list` member, a `dict` key, `UP2-E2002` for any other parameter; Verification: the five `in` cases
  pass, including `["py","in",[200,301,302]]` on `301` and the element-in-front substring form
- [x] 1.4 Add the `exists` action to the shared selector table in `src/uniparser2/ops/htmldom.py`;
  Verification: `["css","exists",S]` is `true`/`false` under all four `on_missing` policies and never
  `Missing`, while `["css","nodes",S]` keeps reporting `Missing`
- [x] 1.5 Add `or` / `and` with **Python's semantics**: one parameter that is an array of references or
  literals; `or` answers with the first truthy operand else the last (`false` when empty), `and` with
  the first falsy else the last (`true` when empty); no `not` action, because `["py","!=",true]` negates
  any boolean; Verification: the five scenarios of the selection requirement pass, and
  `[["const","x"],["ctx","set","locals._a"],["py","or","$locals._a"]]` is `UP2-E2002`

## 2. Tests and conformance

- [x] 2.1 Add `tests/ops/test_predicates.py` with a `@pytest.mark.covers` declaration for each of the
  eleven new pairs and the four policy cases of `exists`; Verification: `uv run pytest
  tests/ops/test_predicates.py` is green (39 cases)
- [x] 2.2 Update the declared counts in `tests/ops/test_registry.py` (operators unchanged, `py` actions
  32 → 41, pairs 61 → 72); Verification: `uv run pytest tests/ops/test_registry.py` is green
- [x] 2.3 Confirm the audit sees the new pairs and no new code; Verification: `uv run up2 conformance
  --check` reports 72 declared pairs = 72 covered pairs and 26 error codes (`PASS`)

## 3. Docs and catalogue

- [x] 3.1 `docs/specs/002` §6.x: the `py` table gains the nine actions with their parameter and result,
  and its function count goes 32 → 41 (the three "closed (31 named functions)" lines and the CSS action
  table's `exists` row are updated too); `docs/specs/004` and `docs/specs/005`'s measured line, plus both
  READMEs, carry the new counts; Verification: the count in `002` matches `uv run up2 ops --json`
- [x] 3.2 `docs/operator-reference.md`: the `py` count 32 → 41, the predicate and selection rows with
  worked examples, the `exists` row and the `nodes`-versus-`exists` note; Verification: every example in
  the new rows is a chain that runs
- [x] 3.3 `tools/demo_report.py`: the nine `py` cases, the `exists` case and the tier counts, then
  re-render `docs/report/up2-report.md` (which embeds the version and the action count); Verification:
  `UP2_UPDATE_REPORT=1 uv run pytest tests/report` followed by a plain run is green, and the rendered
  banner says "72 pairs = 72 pairs covered (0 missing)"
- [x] 3.4 `CHANGELOG.md` (Added: the predicate actions) and `src/uniparser2/__init__.py`
  (`0.3.0` → `0.4.0`); Verification: `uv run up2 --version` prints `0.4.0`

## 4. Gates and wrap-up

- [x] 4.1 Run the definition of done plus the graded change-linter at **L3** with `--project-scope` (the
  change adds public DSL surface: nine `py` actions and one selector action); Verification: ruff ×2,
  format, mypy, `uv run pytest --cov=uniparser2.core --cov-fail-under=95` and `up2 conformance --check`
  pass, and a missing tool is reported truthfully
- [x] 4.2 Archive so the delta creates the `predicates` capability; Verification: `openspec validate
  add-predicate-operators --strict` passes, `openspec list --specs` reports six capabilities, and
  `openspec validate --specs --strict` passes
