# Tasks

## 1. The check

- [x] 1.1 `ops/pyops.py`: `_SCALAR_PARAMS` entries become `(expected, accepted_types)`; `None` means
      "container check only"
- [x] 1.2 `_check_scalar_params`: reject a `Lit` of a type outside the accepted set with `UP2-E1005`,
      the parameter pointer and `_scalar_fix`; keep skipping a `Ref`
- [x] 1.3 `_check_scalar_params`: run the value checks — `slice.spec` through `_parse_slice_spec`,
      `split.maxsplit` through the `_int_param` rule, skipping `null` and `""`
- [x] 1.4 Tests in `tests/ops/test_pyops.py`: the six wrong-typed literals, the two unparsable strings,
      the no-limit spellings, and `join.sep` still coercing

## 2. Docs

- [x] 2.1 `02` §6.4: the `py` table's compile-time validation note covers types and parsed values
- [x] 2.2 `CHANGELOG.md` `[Unreleased]`

## 3. Gates

- [x] 3.1 `uv run ruff format --check`, `uv run ruff check`, `uv run mypy`
- [x] 3.2 `uv run pytest --cov=uniparser2.core --cov-fail-under=95`
- [x] 3.3 `uv run up2 conformance --check`
- [x] 3.4 `change-linter` on the changed Python files
- [x] 3.5 Regenerate the catalogue if the report's bad-chain table changes
