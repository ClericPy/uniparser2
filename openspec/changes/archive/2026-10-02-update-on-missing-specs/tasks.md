# Tasks

## 1. `predicates`

- [x] 1.1 Rewrite the four requirements that name the missing-value policy (`on_missing` / "under every policy") so they state the fixed rules: a missing value is not there, a missing upstream value short-circuits before the action runs, and `exists` answers a boolean without a policy
- [x] 1.2 Fix the Purpose paragraph in `openspec/specs/predicates/spec.md` (a delta cannot carry one for an existing capability)

## 2. `chain-iteration`

- [x] 2.1 Drop "the effective policy" / `on_missing="drop"` / `on_error="raise"` from the two `each` requirements and their scenarios, keeping the per-element rule and the failure propagation

## 3. Verification

- [x] 3.1 `openspec validate update-on-missing-specs --strict` exits 0
- [x] 3.2 `openspec validate --strict` exits 0 and neither spec file mentions `on_missing` / `on_error` any more
- [x] 3.3 Archive the change and confirm the merged `openspec/specs/` text

## 4. Completion record

- [x] 4.1 Tasks 1–3 above were recorded as pending when the change was archived (its plan was written but never
  checked off); the work itself had landed. Every item is checked here because each one is verifiable in the
  repository today: the four `predicates` requirements and the two `chain-iteration` requirements in
  `openspec/specs/` match this change's deltas and carry the fixed rules; neither file matches
  `on_missing` / `on_error` / "effective policy"; `openspec/specs/predicates/spec.md`'s Purpose names no
  policy; and `UP2-E2015` survives only in `openspec/specs/core-evaluator/spec.md`, as the retired number.
  No work was added to this list that the change did not do.
