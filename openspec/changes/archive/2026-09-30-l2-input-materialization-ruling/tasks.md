# Tasks

## 1. The ruling in `003`

- [x] 1.1 §3: drop `input_format` from the seed config example and the field table, and reword the `text`
  paragraph so the seed is described as "carries the caller's inputs verbatim"; Verification: the example
  is valid JSON with comments stripped and contains no key outside `inject`
- [x] 1.2 §3.1 (new): the per-consumer materialization table, the cache contract (scope / key / bound /
  purity / mutation / one implementation), the measured parse and memory numbers, the `bytes` boundary, and
  the deviation record that supersedes the drafts' `input_format`; Verification: every claim in the section
  traces to a measurement taken on this commit (selectolax, 2 MB / 5 MB synthetic HTML) or to a `file:line`
  in `src/`
- [x] 1.3 §4: drop `format` from the parse config example; §4.5 records the deletion of both `input_format`
  and its rename `format` with the reason; Verification: `parse.config` lists only `input`, `policy`,
  `fields`, `route_field`
- [x] 1.4 §11: remove `input_format` from both walkthrough chains and replace the legacy-element row; §11.3
  maps `input_format` to "deleted: materialization is on demand (§3.1)"; Verification: no walkthrough chain
  names a deleted config key

## 2. The neighbouring notes

- [x] 2.1 `docs/specs/001-architecture-and-value-model.md`: the `bytes` invariant now says the caller
  decodes and the consuming operator materializes, instead of the `seed` layer doing both; Verification: the
  invariant still reads as a single testable statement and points at `03` §3.1
- [x] 2.2 `docs/specs/004-persistence-and-sop.md` S1: the input-contract line lists `seed.inject` only;
  Verification: S1's four drafting decisions still match `03` §3 / §4 / §5
- [x] 2.3 `docs/specs/007-source-decisions-and-roadmap.md` §3 (L2): record the ruling and its tie-in to the
  acceptance item "500 items × 20 fields within 3 s"; Verification: the note names the cache as load-bearing
  and the acceptance item it serves

## 3. Verification

- [x] 3.1 `rg 'input_format|parse\.config\.format' docs/` returns only the retirement records; Verification:
  measured — the only hits under `docs/` are `003` §3.1's "both deleted" sentence, its deviation record, the
  §4.5 row, the §11.3 row, and `007`'s ruling banner; no example or config table still uses the key
- [x] 3.2 Every `jsonc` chain in `003` §3 / §4 / §11 parses once its comments are stripped; Verification:
  measured with a one-off script — 7 standalone blocks parse, 3 fragments (`"rows": …`, `"result": …`,
  `"config": …`) are deliberate excerpts and were skipped, 0 failures
- [x] 3.3 The change validates as a design-only change; Verification: `openspec validate
  l2-input-materialization-ruling --strict` passes with `skip_specs: true`, `openspec validate --specs
  --strict` passes for all five capabilities, and archiving reports 0 spec updates
