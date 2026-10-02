# Design

## The trace is a debugging aid, not the replay format (O6)

`03` §4.4 says "with the answers recorded, a flow replays deterministically". That sentence is about
the **answers**: what makes a run replayable is the host's own log of the suspensions it answered
(the request it sent, the response it got, the receipt the function returned), together with the
run's input. The trace is deliberately not that log. It records what the **kernel** did stage by
stage, and it is lossy by construction: every value is replaced by `type` / `preview` (200 characters)
/ `size`, the full value living only in the trace object's memory, which dies with the process.
Stretching it into a replay format would mean (a) making it complete, so a trace would carry whole
documents, (b) making it a **contract**, with a version, a fingerprint and compatibility rules, and
(c) putting the host's answers into it, which is host data, not kernel data. So O6 is settled as:
**the trace is a debugging aid; the replay format stays the host's answered-suspension log, which
this change does not define.** `003` §13 marks it settled and `006` §5.1 records the ruling.

## One event per evaluated stage, and one per suspension

`003` §4.4's earlier row said "one per step". That is what the trace would have looked like without
a hook in the evaluator, and it is not enough: a step's `parse` field map holds several chains, each
with several stages, and "which stage produced this" is the question the bench exists to answer. So
the unit is the **evaluated stage**, and a suspension is a second event kind, because "it handed the
host a batch of 20 tasks here" is not a stage's product.

Both kinds share the sequence, so one list renders as the `06` §3 table in order:

| Column of `06` §3 | Where it comes from |
|---|---|
| `#` | `seq` (1-based, in evaluation order) |
| `Step` | `step` (the step name; `null` for a chain run by `up2 trial` outside a story) |
| `Field` | `field` (the field-map key the chain was compiled as, innermost wins) |
| `Do` | `op.action` for a stage, `effect:<kind>` for a suspension |
| `Input` / `Output` | the `type` / `preview` / `size` view of the value entering and leaving |
| `State` | `Ok` / `Missing` / `Failed`; a suspension is `Ok` and carries `effect` |

A stage that is never evaluated writes no event: the short-circuit (`01` §4) ends the chain, so a
`Failed` or uncaught `Missing` stage is the last event of its chain — which is exactly the row a
reader wants to see last.

## `field` and `item`: the two locators

`item` has two sources, because a story fans out in two different places:

- **`each`** (inside a chain) creates one child scope per element, in input order, and hands that
  scope the element's position (`Scope.child(iteration=…)`, additive: a caller with no fan-out
  position leaves it out). The evaluator reports the scope's `iteration` as `item`. The position
  comes from the operator that owns the fan-out rather than from a run-wide counter, because a run
  can fan out several times and each fan-out numbers its own elements from 0.
- **A `RequestBatch`** (a step-level effect) runs its receiving step once per answer, and no scope is
  involved. The story layer numbers that loop itself and passes the answer's position down, so the
  events of the third answer's receiving step say `item: 2`.

When both are active (an `each` inside a receiving step), the **innermost** index wins: the event is
about the field chain that is running, and that chain is iterating the inner list. A nested fan-out
therefore shows the innermost index; the outer one is recoverable from the event order, and making
`item` a path would have been a second, incompatible shape for `06` §5.1's scalar field.

`field` comes from the compiled data rather than from bookkeeping: `compile_field_map` already names
each chain for diagnostics, so `CompiledField` now carries that name (`""` for a top-level chain) and
the evaluator reports it. That is what makes a missing `title` inside an `each` distinguishable from
a missing `price` inside the same map.

## Values are not sent back in full

`value_view` builds `type` / `preview` / `size` from one rendering of the value, `values.text_of`,
which `preview` already used: a JSON value is its JSON text, a host object is its type name plus a
truncated `repr`, an `Opaque` handle is `<opaque X>`. `size` is the length of that **full** text and
`preview` is its first 200 characters with the repository's `...(+N)` marker — so a reader can see how
much was cut, and `get_value(seq)` fetches the value itself from the trace's own memory. The trace
therefore holds a strong reference to every value it previewed, for as long as it lives; that is the
price of "expand on demand", and it is paid only by a caller that asked for a trace.

## Compiled parameters, not the author's wording

`params` is the compiled named-parameter tree of `02` §4: defaults are filled in, the action slot's
presets have already joined, and every leaf says what it is — `{"kind": "ref", "target":
"globals.base_url"}` or `{"kind": "lit", "value": "..."}`. An `each` parameter carries its compiled
field map as `{"kind": "fields", "fields": {"url": {"kind": "chain", "stages": [...]}}}` so the
nesting is visible without a second event kind. A `call` step's `with` tree is rendered the same way,
which is why the effect event can carry it in `params` while `output` carries the arguments that were
actually handed over.

## Where the trace lives, and what it costs

`core/trace.py` (stdlib only, no IO, synchronous), driven by the same layer that runs the story: the
CLI or a UI creates a `Trace`, passes it to `start` / `eval_field`, and reads `trace.events`,
`trace.to_list()` and `trace.get_value(seq)`. Nothing is collected unless the caller passes a trace:
`stamp(None)` returns `0.0` without reading the clock, `elapsed_ms` answers `0.0` for it, and the
evaluator's only added work in that mode is one `if trace is not None`. `core/` therefore keeps its
invariants (`01` §1.1) and an ordinary run is bit-for-bit the run it was before.

## Rejected alternatives

| Alternative | Why not |
|---|---|
| A trace event per **step** only (`003` §4.4's old row) | a step's field map hides which chain failed; the bench's whole job is "which stage" |
| Sending the full values in the event | `06` §5.1 asks for `preview` + `size` and an on-demand fetch; a 20-item fan-out over 5 MB pages would make the event list the memory problem it is meant to diagnose |
| A second list of events for the effect suspensions | one ordered list is what `06` §3 renders; a second list would make "it suspended here" a lookup instead of a row |
| Deriving `item` from a run-wide child counter | a run may fan out several times, and the second `each` would then start where the first stopped; the element's position is the fan-out operator's own fact, not a counter's |
| Deriving `field` by threading the name through the sub-chain runner | it would change `ChainRunner`, the operator-facing contract, for information the compiled chain already owns |
| Making `state` of an effect event a fourth value (`Suspended`) | `06` §5.1 fixes the vocabulary at `Ok` / `Missing` / `Failed` and gives the effect its own `effect` key; a suspension is not an error (`03` §5) |
| A new error code for a trace problem | there is no trace error to report: a trace cannot fail a run, and a retired number is never reused |
