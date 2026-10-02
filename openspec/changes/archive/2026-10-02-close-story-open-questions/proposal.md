# Close the two small open questions of `03` §13

## Why

`03` §13 has recorded two small questions in the same subsystem since the story executor landed, and
both are decided by rules the codebase already applies elsewhere:

- **O11**: a step whose chain product is `Missing` flows into the collected exit list as `null`. That
  invents a value where there is none, while `01` §4.2 says a missing value is *not there* — a field map
  drops the key and a batch skips the item. The step boundary is the one place that still disagreed.
- **O12**: a dotted reference may resolve a **callable** attribute (`$resp.json` becomes a bound method),
  while `py.getattr` has refused one since the object-value change. The value could never leave the run
  (`pack`, `UP2-E2003`), so the failure exists either way — it is just later and less clear than
  `getattr`'s.

## What Changes

- **A step whose chain product is `Missing` is skipped.** No product is recorded, and the exit collects
  nothing for it, so the output list holds only the products that exist. The same rule then covers a
  receiving step: when the step `next` names produces nothing, the run continues at the step after it
  instead of handing on a `null`. `03` §9 states the rule and `03` §13 O11 is marked settled.
- **A dotted reference refuses a callable attribute**, with the same code (`UP2-E2002`), the same message
  shape and the same fix hint `py.getattr` uses, so an author sees one rule and not two. `03` §13 O12 is
  marked settled and the reference section of `002` §3.1 states it.
- No DSL syntax change, no new error code and no new dependency.

## Capabilities

### New Capabilities

None. Both rules belong to the capabilities that already own the value domain, the story layer and the
reference path.

### Modified Capabilities

- `core-evaluator`: a missing value has a fixed outcome at the step boundary (the step is skipped) and at
  a reference path (a callable attribute is refused, as `getattr` refuses one).
- `chain-iteration`: the run's output is the exit step's products **that exist**, and a step that
  produced nothing is skipped rather than contributing a null.

## Impact

- Kernel: `core/story.py` (the boundary returns "no product" and the run continues past it) and
  `core/refs.py` (`_walk_attribute` refuses a callable).
- Docs: `03` §9/§13 O11/O12, `002` §3.1.
- Tests: `tests/chains/test_story.py` (a skipped step contributes nothing to the exit, a skipped
  receiving step, and no product recorded for a later reference) and `tests/runtime/test_runtime_errors.py`
  (the callable refusal and its agreement with `py.getattr`).
- Conformance: unchanged (no new code, no new operator/action).
