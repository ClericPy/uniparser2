# Tasks

## 1. The predicate and the boundaries

- [x] 1.1 `core/values.py`: `is_json_value` requires `math.isfinite` for a float
- [x] 1.2 `core/export.py`: the fix line says a float must be finite
- [x] 1.3 `core/ast.py`: `loads` rejects `-Infinity` / `Infinity` / `NaN` through `parse_constant`
      with `UP2-E1004`; `dumps` passes `allow_nan=False` and converts the encoder error to the same code
- [x] 1.4 Tests: the predicate, `pack` top-level and nested, `loads`, `dumps`, a finite float unchanged,
      and `py.float("1e999")` still answering `inf` mid-chain

## 2. Docs

- [x] 2.1 `01` §4 / `02` §7: the value domain excludes a non-finite float (`UP2-E2003` / `UP2-E1004`)
- [x] 2.2 `CHANGELOG.md` `[Unreleased]`

## 3. Gates

- [x] 3.1 `uv run ruff format --check`, `uv run ruff check`, `uv run mypy`
- [x] 3.2 `uv run pytest --cov=uniparser2.core --cov-fail-under=95`
- [x] 3.3 `uv run up2 conformance --check`
- [x] 3.4 `change-linter` on the changed Python files
- [x] 3.5 `up2 trial --json` on an `inf`-producing chain reports the diagnostic instead of `Infinity`
