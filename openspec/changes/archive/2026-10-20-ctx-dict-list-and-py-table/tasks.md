# Tasks

## 1. `ctx` names its result shape

- [ ] 1.1 `ops/ctx.py`: replace `map` with `dict` and `list`; each compiles its own path set and the
      `_collect_paths` dispatch goes away
- [ ] 1.2 Tests: the `ctx.map` cases become `ctx.dict` / `ctx.list`; the old action is `UP2-E1002`
- [ ] 1.3 Docs: `02` §6.8, `docs/operator-reference.md`

## 2. `py.items`

- [ ] 2.1 `ops/pyops.py`: the action, its summary (including "index with the literal 0 / 1") and its
      implementation
- [ ] 2.2 Tests: a mapping becomes pairs; the pairs feed `each`; a non-mapping fails
- [ ] 2.3 Conformance: the new `(py, items)` pair has its case; `py` holds 42 functions

## 3. The conversion fix text

- [ ] 3.1 `ops/pyops.py` `_convert`: state the expected input and the upstream stage; no fallback advice
- [ ] 3.2 Tests: a conversion failure's `fix` names no other operator

## 4. Docs and the local report tool

- [ ] 4.1 `tools/demo_report.py`: the `ctx.set` note no longer names `fields`; cases for `ctx.dict`,
      `ctx.list` and `py.items`
- [ ] 4.2 `02` §6.4 and the regenerated `docs/report/up2-report.md`; `CHANGELOG.md` `[Unreleased]`

## 5. Gates

- [ ] 5.1 `ruff format --check`, `ruff check`, `mypy`
- [ ] 5.2 `pytest --cov=uniparser2.core --cov-fail-under=95`
- [ ] 5.3 `up2 conformance --check`
