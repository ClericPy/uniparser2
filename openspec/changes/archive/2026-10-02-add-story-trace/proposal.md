# Add the story trace

## Why

`06` §5.1 defines the `TraceEvent` a trial bench renders row by row, and `06` §2 makes
`up2 trial --trace` the CLI baseline of that bench, but no slice has built either: `004` §7-S3 even
carries a "Corrected" note saying the flag does not exist, and `06` §10's acceptance item 4 ("click
run") cannot be met. The consequence is the one thing the SOP cannot answer today: `04` §7-S3 says a
chain that runs is not a chain that extracted the right content, and `04` §9 row 8 names the exact
mistake only a trace can reveal ("forgot the `each` stage, so the fields ran once over the whole
page" — a wrong product, not an error). Without a per-stage view, that mistake is invisible.

`03` §13 **O6** is the open question this change also has to settle: how far the trace goes, and
whether a recorded run **is** the replay format.

## What Changes

- **A trace in the kernel** (`core/trace.py`): one `TraceEvent` per **evaluated stage**, plus one per
  **effect suspension**. The stage event carries the fields of `06` §5.1 — `seq`, `step`, `item`,
  `field`, `stage`, `op`, `action`, `params`, `input`, `output`, `state`, `detail`, `ms` — where
  `params` are the **compiled** parameters, `input` / `output` are a `type` / `preview` (200 chars) /
  `size` view instead of the whole value, and `item` is the fan-out index that makes "the third
  result's title is missing" locatable.
- **Values on demand**: `Trace.get_value(seq)` returns the full input or output value a preview
  stands for, so a UI never ships a 5 MB document through the event list.
- **Effect events**: `request` / `batch` / `call` suspension events record what the kernel handed
  out (`"effect": "batch"`, the task list in `output`), so a UI can show "it suspended here, and this
  is what it handed out". A `call` carries the function name in `action` and its compiled `with`
  tree in `params`.
- **The executor gains an optional hook, and nothing else**: `eval_field(..., trace=...)` and
  `start(bundle, value, trace=...)`; a run without a trace behaves exactly as before (no clock read,
  no event, no position bookkeeping).
- **`up2 trial --trace [--json]`**: the flag `004` §7-S3 and `06` §2 name, reporting the run's events
  in evaluation order. Since a CLI has no host, a story run stops at its first suspension and the
  trace ends at the effect event that suspended it.
- **O6 is settled**: a recorded run is **not** the replay format; the trace is a debugging aid.
  Recorded in `003` §13 (the way the earlier settled items are) and in `006` §5.1.
- **Docs**: `003` §4.4 (the per-step row is superseded by the per-stage one), `003` §13-O6,
  `006` §5.1 (the effect shape, `get_value`, the item rule, the O6 ruling), `004` §7-S3 / §7.1 / §8
  (`--trace` exists now), `CHANGELOG.md`.

## Capabilities

### New Capabilities

- `story-trace`: the trace's data structure, its fidelity rule (previews plus on-demand values), its
  fan-out locator, and the CLI flag that exposes it.

### Modified Capabilities

None. `core-evaluator`'s requirements are unchanged: the optional hook adds no observable behavior to
a run that does not ask for a trace.

## Impact

- Kernel: new `core/trace.py`; `core/evaluator.py` gains the optional `trace` hook; `core/story.py`
  gains the run's trace, the step/field position and the effect events; `core/refs.py` numbers a
  child scope's iteration; `core/ast.py` + `core/compile.py` record the field-map key a chain was
  compiled as; `core/values.py` extracts `text_of`; both `__init__.py` re-export the trace.
- CLI: `cli/main.py` gains `trial --trace` and its text/JSON output.
- No error code is added and no retired number is reused; `core/` stays stdlib-only, IO-free,
  synchronous, and a chain without a trace pays nothing.
- Docs: `003` §4.4/§13, `006` §5.1, `004` §7-S3/§7.1/§8, `CHANGELOG.md`.
- Tests: `tests/chains/test_trace.py`, `tests/cli/test_cli.py`; conformance stays green (73 pairs,
  35 codes — the registry is untouched).
