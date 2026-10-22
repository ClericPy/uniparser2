# Proposal

## Why

One fact — "the query matched nothing" — is carried by a third outcome state, and every operator, field
map, step and trace has to reason about it. That state is the only reason `accepts_missing` and
`py.default` exist, and the documentation has already drifted from the code: `py.or` is described as
catching it and cannot. A reader cannot tell from a chain what will happen when a selector finds
nothing, and the engine cannot say either, because the answer depends on a per-action flag.

## What Changes

- **The outcome type has two variants**, `Ok` and `Failed`. The `Missing` variant is removed. **BREAKING**
- **A query that matches nothing yields the empty value of its shape** — `""` for text accessors, `[]`
  for list accessors, `None` for element handles — as a value that flows on. **BREAKING**
- **A reference path that cannot be walked is a failure** (`UP2-E2001`), never an empty value. **BREAKING**
- **`accepts_missing`, the `MISSING` sentinel and the evaluator's missing branch are deleted**;
  `py.default` keeps only its `None` / `""` behaviour. **BREAKING**
- **A field map has no absent key**: every field yields a value or fails the run.
- **A step always produces a product or fails**: the "a missing product skips the step" rule and the
  internal sentinel behind it are removed.
- **The trace records `Ok` or `Failed` only.**

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `core-evaluator`: the outcome is two states; a path that cannot be walked is a failure; a step always
  produces a product or fails.
- `chain-iteration`: no absent field inside an element, no skipped step, and an element whose queries all
  matched nothing still yields its keys.
- `dsl-operators`: every query action's no-match result is specified as the empty value of its shape.
- `story-trace`: the event state vocabulary is `Ok` / `Failed`.

## Impact

- Kernel: `errors`, `values`, `registry`, `ast`, `compile`, `evaluator`, `refs`, `story`, `trace`.
- Operators: `htmldom`, `xmlxpath`, `jsonquery`, `regex`, `pyops`, `basic`.
- Docs: notes `01` §4, `02` §5 and the action table, `03` §9, `04` §7's counter-examples,
  `docs/operator-reference.md`, both READMEs, `CHANGELOG.md`, and the regenerated report.
- Tests: every expectation that asserts `Missing`, plus a per-operator table of empty values.
