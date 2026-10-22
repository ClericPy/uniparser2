# Name the entry step, and let a reference stand in for a whole chain

## Why

Two asymmetries in the story format are visible in the committed samples. The run's **end** is declared
(`exit` names the step whose products are collected) while its **start** is implicit — "the first step in
the array" — so nothing in a bundle says where the run begins, and a step that no `next` reaches and
that is not first is silently dead. And a step whose value *is* its own input has to be written as a
stage: `["py","id",""]` exists only to return its input unchanged, which is what a reference already
means everywhere else in the DSL (`"rows": "$in"`).

## What Changes

- **`entry` becomes a required top-level key**, symmetric with `exit`: the run starts at that step with
  the caller's value. `up2 lint` names the entry in its output, and lint checks that `entry` names an
  existing step.
- **Lint reports steps unreachable from the entry** — the new `UP2-E1018`, pointing at the unreachable
  step. Today such a step is dead code nothing reports.
- **A chain may be a reference**: wherever a chain is expected (a field-map value, or a step's `parse`
  when it is an array), a string that begins with `$` is accepted and means "the value the reference
  names, unchanged". This is the same spelling `args` already uses for an argument, and it is the only
  way to express identity — **no single-element stage form is added**.
- **`py.id` is deleted** with every use of it: the reference form replaces it. `py`'s function count goes
  42 → 41. **BREAKING** for a chain that writes `["py","id",""]`.
- **The identity stages leave both samples.** A chain's first stage already receives the input (`02` §5),
  so `[["py","id",""], ["py","urljoin", …]]` is exactly `[["py","urljoin", …]]`, and `{"url": ["$in"]}`
  collapses to `{"url": "$in"}`.
- **Both sample hosts take the seed URL from the command line** (defaulting to the site root) and stop
  passing `globals.base_url` as the seed: `base_url` is the urljoin base, not the seed.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `chain-iteration`: a bundle REQUIRES `entry`; a step unreachable from the entry is rejected at compile
  time; a chain MAY be written as a `$` reference; `py.id` is removed from the action set.
- `dsl-operators`: the `py` function table loses `id`, and the catalogue reflects it.

## Impact

- Kernel: `core/story.py` (`entry`, the unreachable-step lint, the start position); `core/compile.py` +
  `core/ast.py` + `core/evaluator.py` + `core/trace.py` (a whole-chain reference); `core/errors.py`
  (`UP2-E1018`); `ops/pyops.py` (the `id` entry and `_py_id` deleted).
- Samples: both `samples/*/site.json` (identity stages, `entry`) and both `samples/*/host.py` (the seed
  argument).
- Docs: `03` §2/§5/§10/§11/§13, `002` §5/§6.4, both READMEs, `docs/operator-reference.md`, the
  regenerated `docs/report/up2-report.md`, and a `CHANGELOG.md` `[Unreleased]` entry.
- Conformance: 73 → 72 declared pairs (one `py` action fewer), one new error code.
