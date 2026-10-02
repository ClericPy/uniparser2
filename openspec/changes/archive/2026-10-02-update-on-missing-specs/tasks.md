# Tasks

## 1. `predicates`

- [ ] 1.1 Rewrite the four requirements that name the missing-value policy (`on_missing` / "under every policy") so they state the fixed rules: a missing value is not there, a missing upstream value short-circuits before the action runs, and `exists` answers a boolean without a policy
- [ ] 1.2 Fix the Purpose paragraph in `openspec/specs/predicates/spec.md` (a delta cannot carry one for an existing capability)

## 2. `chain-iteration`

- [ ] 2.1 Drop "the effective policy" / `on_missing="drop"` / `on_error="raise"` from the two `each` requirements and their scenarios, keeping the per-element rule and the failure propagation

## 3. Verification

- [ ] 3.1 `openspec validate update-on-missing-specs --strict` exits 0
- [ ] 3.2 `openspec validate --strict` exits 0 and neither spec file mentions `on_missing` / `on_error` any more
- [ ] 3.3 Archive the change and confirm the merged `openspec/specs/` text
