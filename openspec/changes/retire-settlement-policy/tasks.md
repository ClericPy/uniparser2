# Tasks

## 1. Kernel

- [ ] 1.1 `core/evaluator.py`: delete `Policy`, `DEFAULT_POLICY`, `MISSING_STRATEGIES`, `ERROR_STRATEGIES` and the settlement branches; the rules become fixed (missing → the key is absent from a product / the item is skipped; failed → raise with code and pointer)
- [ ] 1.2 Drop the `policy` parameter from `eval_field` and the retired names from `core/__init__.py`
- [ ] 1.3 Retire `UP2-E2015` in `core/errors.py` (the number is not reused)

## 2. CLI and callers

- [ ] 2.1 Remove `--on-missing` / `--on-error` from `up2 trial`; its output shape is otherwise unchanged
- [ ] 2.2 Update every in-repo caller (`tests/`, `tools/`, `demo.py`) to the new signature

## 3. Tests

- [ ] 3.1 Delete the policy-matrix tests; rewrite the cases that assert `""` for a missing value to assert the key's **absence**
- [ ] 3.2 Add one case per fixed rule: a missing field is absent from the product; a failed stage raises with its code and pointer

## 4. Docs

- [ ] 4.1 `01` §5: replace the settlement table with the two fixed rules; amend `N4`; record the retirement in the deviation records
- [ ] 4.2 `02` §7.1 (the retired code), `03` §2 and §11 (no `policy` block), `04` (the SOP's drafting checklist)
- [ ] 4.3 Re-render `docs/report/up2-report.md`
