# Update the specs that still describe the settlement policy

## Why

`retire-settlement-policy` removed the settlement policy from the kernel, the story JSON and the CLI, and
synced the design notes. Two capability specs were left behind: `predicates` and `chain-iteration` still
tell a reader that an outcome is decided by `on_missing` / `on_error` — parameters and a story block that
no longer exist. A spec that describes a retired parameter is worse than no spec at all: the next
implementer would add it back.

## What Changes

- `predicates`: the Purpose paragraph and the four requirements that name the missing-value policy
  (comparisons, `in`, the selection actions, the selector family) are reworded to the two fixed rules —
  a missing value means "not there", and a missing upstream value short-circuits before the action runs.
  `css.exists` keeps answering `true` / `false`, with no policy to consult.
- `chain-iteration`: the two `each` requirements that name "the effective policy" drop it, together with
  the `on_missing="drop"` / `on_error="raise"` evaluations in their scenarios. What did not change stays
  verbatim: per-element scopes, one dictionary per element, and a failure propagating with its own code.

## Impact

- Two files under `openspec/specs/` (`predicates`, `chain-iteration`) get corrected wording.
- No code, no chain behaviour and no design-note change: this is wording catching up with
  `retire-settlement-policy`. The `predicates` Purpose is edited in place, because a delta cannot carry a
  Purpose for a capability that already has one.
