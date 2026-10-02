# Design — retire the settlement policy

## Context

See `proposal.md` — Why. The policy is threaded through the evaluator (four missing strategies, four error
strategies), the `eval_field` signature, the CLI (`--on-missing` / `--on-error`) and the tests. The
tri-state itself (`Ok` / `Missing` / `Failed`) stays: only its configurable settlement goes.

## Goals / Non-Goals

- Goal: one fixed behaviour — missing is "not there", failed always raises — reachable without configuration.
- Non-goal: changing the tri-state, `accepts_missing`, or the actions that can catch a missing value.
- Non-goal: keeping backward compatibility (the project is pre-1.0 and the in-repo callers are updated in
  the same change).

## Decisions

1. **Missing means absence, at both levels.** In a field map the key is dropped from the product; in a batch
   the item is skipped. *Alternative rejected*: `null` — it makes every record carry keys whose meaning is
   "the page did not have this", which is exactly the noise the record should not have.
2. **Failed always raises.** The safe default becomes the only behaviour.
   *Alternative rejected*: keeping a degrade-to-empty option — it silently turns a broken selector into
   empty data, which is the failure mode this project exists to avoid.
3. **The fallback lives at the action level.** `py.default` and `py.or` already catch a missing value
   (`accepts_missing`), so a story that wants "use `""` if absent" writes it where it applies instead of
   reconfiguring the whole run. *Alternative rejected*: a per-field policy — it is a second place to express
   the same fact, which is what the story-level `policy` block already was.
4. **"Required" is the type's business.** A field that must exist is enforced by the host-registered type
   constructor at the step boundary (`Article(**fields)`), which already reports the missing key at the step
   that produced it.
5. **Retire `UP2-E2015` without reusing its number**, per the project's error-code rule, so an old reference
   still points at the same meaning.

## Risks / Trade-offs

- Removing a keyword argument breaks any caller outside this repository → acceptable pre-1.0; the design
  notes (`01` §5) and the deviation records state the retirement.
- A missing field is now silent in the product → the trace still shows the `Missing` state per field, which
  is where an author sees it; a strict check belongs to the type constructor.

## Open Questions

- None: the remaining question (whether a field-level override is ever worth adding) is deferred until a
  real story needs it, and adding it later changes no rule stated here.
