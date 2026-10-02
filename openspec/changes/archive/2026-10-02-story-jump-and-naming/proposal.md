# Story jumps and the naming that makes them readable

## Why

The story format of `03` §2 was written before anything ran it. Running the two sample sites through
it exposed three gaps that only the data shape can close:

1. **The exit is derived from "the last step".** That was true while execution was strictly linear.
   A story that routes responses to the step that parses them (a jump) has no unique last step, so
   the exit must be **named**.
2. **A parse rule could only be a named chain.** The `chains` table was a second namespace for
   exactly the same thing a step is (a field chain over one input), and a per-task `chain` made the
   host, not the kernel, decide what happens to an answer. A parse rule is a step.
3. **A step had no way to name its own input.** Reading it took `["ctx","set","locals._page"]`
   gymnastics, and a step whose value *is* its input had no honest identity action
   (`["py","str",""]` was the workaround, and it converts anything that is not a string).

The naming gap is part of the same problem: `key` and `out` read as generic JSON words, while the
model means a step's **name** and its product **type**.

## What Changes

- **BREAKING — step keys are renamed**: `key` → `name`, `out` → `type`. Nothing else about a step
  changes.
- **BREAKING — the `chains` table is deleted.** A parse rule is a step; the bundle keeps `globals`
  and `steps` only.
- **`next`** on a step whose `type` is `Request` or `RequestBatch`: it names the **step that
  receives the responses**. It is the step-level default, and a single task item may carry its own
  `next` and override it. **The kernel resolves it — the host never sees `next`** (it is stripped
  from the task before the request is handed over), so the host sends and nothing else.
- **`exit`** (top-level, required): names the step whose products form the run's output, collected
  **in order as a list**. With jumps, "the last step" is no longer unique, so the exit is declared.
- **`$in`**: a reference root naming **this step's own input**, so a step reads `$in.url` without
  the `ctx.set locals._page` detour. It is a reserved root next to `globals` / `locals` / `fields`.
- **New action `["py","id",""]`**: returns its input unchanged (no arguments). It replaces the
  `["py","str",""]` workaround for a step whose value *is* its input (a seed URL).
- **The first story executor**, which is what makes any of the above real: `start(bundle, value) ->
  run`, `run.next()`, `run.send(answer)`. A `Request` / `RequestBatch` suspends the run and the
  answer resumes the **same** run; `call` suspends and resumes with the receipt; `next` and `exit`
  are resolved inside the kernel. `up2 lint` and `up2 trial` accept a **story file** (a JSON object
  with `steps`) in addition to today's field-chain file.
- **Both sample site bundles are rewritten** to the new keys, and re-run through the real executor
  against their live sites.

**Out of scope** (explicitly, to keep this change's surface honest): the materialization cache of
`03` §6, the Store, the trial UI, pagination, and the registered-type constructor (§3.2) — `type` is
validated as a declared name, not constructed.

## Capabilities

### New Capabilities

None. The story format and its executor belong to the capability that already owns the chain layer's
structure; introducing a second one would split one format across two specs.

### Modified Capabilities

- `chain-iteration`: the story bundle's shape and its execution are added — the step keys `name` /
  `type`, the deletion of `chains`, `next` with its per-task override, the required top-level
  `exit`, the `$in` reference root, the `py.id` action, the suspend/resume run loop and the CLI
  entry points that accept a story file. The existing `each` requirements are unchanged.

## Impact

- Kernel: new `core/story.py` (compile + run loop); `core/refs.py` (`$in` as a reserved root, the
  step input on `Scope`); `core/evaluator.py` (the parameter resolution seam the `call` step reuses);
  `core/values.py` / `core/errors.py` (two new codes: `UP2-E1009` and `UP2-E1016`).
- Operators: `py.id` (new entry in the `py` table); `py.getattr` (from `allow-object-values`) becomes
  the way a story reads an answer.
- CLI: `up2 lint` / `up2 trial` branch on "a JSON object with `steps`".
- Docs: `03` §2, §2.1, §4, §5, §10, §11, §12, §13; `007`'s L2 roadmap row; both `samples/*/site.json`;
  the READMEs' "not there yet" paragraph.
- Tests: story compile/run cases, the new codes, the CLI story path.
