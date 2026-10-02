# Retire the settlement policy

## Why

The settlement policy is configuration nobody needs. `on_error` already defaults to `raise`, which is the
only safe default; `on_missing` defaults to `empty`, which writes `""` into a record when a selector never
matched — a lie in the data. "This field may be absent" and "this field must exist" are answered by the
missing default and by the host-registered type constructor, and tolerating one failure is what the
action-level `py.default` / `py.or` are for. Four strategies, a `policy=` parameter, two CLI flags and a
block in every story exist to configure an escape hatch that is better expressed locally.

## What Changes

- `Policy`, `DEFAULT_POLICY`, `MISSING_STRATEGIES` and `ERROR_STRATEGIES` are deleted; `eval_field` loses its
  `policy` parameter; `up2 trial` loses `--on-missing` and `--on-error`.
- The rules become fixed and unconditional:
  - **missing means "not there"** — the key is absent from a field-map product, the item is skipped in a
    batch; no `""`, no `null` is invented;
  - **failed always raises**, carrying its code and JSON Pointer.
- `UP2-E2015` ("value is missing and the effective policy is raise") is retired and its number is not
  reused.
- The `policy` block disappears from the story JSON (`03` §2); the tri-state itself is untouched — only its
  configurable settlement is retired.

## Impact

- Kernel: `core/evaluator.py` (the strategy branches and the parameter), `core/errors.py`, `core/__init__.py`
  (the exported names), `cli/` (the two flags).
- Tests: every case that asserts `""` for a missing value, the policy matrix in `tests/`, and the CLI tests
  that pass the flags.
- Docs: `01` §5 (the settlement table is replaced by the two fixed rules) and `N4`, `02` §7.1 (the retired
  code), `03` §2 and §11 (no `policy` block), `04` (the SOP's drafting checklist), `docs/report/up2-report.md`.
