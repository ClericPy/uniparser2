# Tasks

## 1. Kernel: two outcomes

- [ ] 1.1 `core/errors.py`: remove the `Missing` variant from the outcome union; keep `UP2-E2001`'s meaning
- [ ] 1.2 `core/values.py`: remove the `MISSING` sentinel and its documentation
- [ ] 1.3 `core/registry.py` + `core/ast.py` + `core/compile.py`: remove `accepts_missing` from the action
      spec, the compiled stage and the passthrough
- [ ] 1.4 `core/evaluator.py`: remove the missing branch; a failure always stops the chain
- [ ] 1.5 `core/refs.py`: an absent key or unwalkable path is `Failed` with `UP2-E2001` (two sites)

## 2. Operators: the empty value of each shape

- [ ] 2.1 `ops/htmldom.py`: `text` / `@attr` / `html` / `outer` → `""`, `nodes` → `[]`, `self` → `None`
- [ ] 2.2 `ops/xmlxpath.py`: `text` / `nodes` → `[]`, `self` → `None`
- [ ] 2.3 `ops/jsonquery.py`: a query that matched nothing → `None`
- [ ] 2.4 `ops/regex.py`: `search` / `group` → `""`, `findall` → `[]`
- [ ] 2.5 `ops/pyops.py`: `first` / `last` over an empty list → `None`; `parse_time` over empty text →
      `""`; drop `accepts_missing` from `default`; update the action summaries that mention "absent ⇒ Missing"
- [ ] 2.6 `ops/basic.py`: `each` no longer has an absent-field branch

## 3. Story and trace

- [ ] 3.1 `core/story.py`: a field map has no absent key; remove `_PRODUCT_UNAVAILABLE` and the skipped-step
      rule; a step always produces a product or fails
- [ ] 3.2 `core/trace.py`: `state` is `Ok` or `Failed`; remove `STATE_MISSING`

## 4. Docs and notes

- [ ] 4.1 `01` §4: the outcome model, the empty-value rule, and `D-01-1`'s replacement rationale
- [ ] 4.2 `02` §5 and the action table: the per-action no-match column; remove "absent ⇒ Missing"
- [ ] 4.3 `03` §9 and §4: no skipped step, no absent field
- [ ] 4.4 `04` §7's counter-examples, `docs/operator-reference.md`, both READMEs, `CHANGELOG.md`

## 5. Tests and the report

- [ ] 5.1 Update every `Missing` expectation to the empty value or the failure it now is
- [ ] 5.2 A per-operator table test: each no-match action answers the empty value of its shape
- [ ] 5.3 Regenerate `docs/report/up2-report.md` (`UP2_UPDATE_REPORT=1`)

## 6. Gates

- [ ] 6.1 `ruff format --check`, `ruff check`, `mypy`
- [ ] 6.2 `pytest --cov=uniparser2.core --cov-fail-under=95`
- [ ] 6.3 `up2 conformance --check`
- [ ] 6.4 Both samples re-run through their host scripts
